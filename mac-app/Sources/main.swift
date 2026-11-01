import AppKit
import UniformTypeIdentifiers
import Darwin

struct AvatarProfile: Codable { let version:Int; let name:String; let photo:String; let audio:String; let text:String }

enum ScriptInput {
    static func speech(_ source:String)->String? {
        let pattern = #"(?i)озвучка\s*:\s*(?:«([^»]+)»|“([^”]+)”|"([^"]+)")"#
        let regex = try! NSRegularExpression(pattern:pattern)
        let ns=source as NSString
        let lines=regex.matches(in:source,range:NSRange(location:0,length:ns.length)).compactMap { match -> String? in
            for index in 1..<match.numberOfRanges where match.range(at:index).location != NSNotFound {
                return ns.substring(with:match.range(at:index)).trimmingCharacters(in:.whitespacesAndNewlines)
            }
            return nil
        }
        return lines.isEmpty ? nil : lines.joined(separator:"\n")
    }
    static func issue(_ source:String)->String? {
        let text=source.trimmingCharacters(in:.whitespacesAndNewlines)
        if speech(text) != nil { return "Это режиссёрское задание. Нажмите «Извлечь озвучку», затем проверьте реплики. Указания сцен не исполняются движком." }
        let count=text.unicodeScalars.count
        if count == 0 || count > 1500 { return "Текст озвучки: \(count) символов. Допустимо 1–1500. Вставьте только произносимые слова." }
        let regex=try! NSRegularExpression(pattern:#"(?<=[.!?])\s+|\n+"#)
        let range=NSRange(text.startIndex...,in:text)
        let split=regex.stringByReplacingMatches(in:text,range:range,withTemplate:"\n").components(separatedBy:"\n")
        if split.contains(where:{$0.trimmingCharacters(in:.whitespacesAndNewlines).unicodeScalars.count > 350}) {return "Разбейте длинную реплику новой строкой: максимум 350 символов в одной реплике."}
        return nil
    }
}

final class IconButton: NSButton {
    private var hoverArea: NSTrackingArea?
    private var hovering=false
    var primary=false {didSet {refreshAppearance()}}
    override var isEnabled: Bool {didSet {refreshAppearance()}}
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let area=hoverArea {removeTrackingArea(area)}
        let area=NSTrackingArea(rect:.zero,options:[.mouseEnteredAndExited,.activeInActiveApp,.inVisibleRect],owner:self,userInfo:nil)
        addTrackingArea(area); hoverArea=area
    }
    override func mouseEntered(with event:NSEvent) {hovering=true; refreshAppearance()}
    override func mouseExited(with event:NSEvent) {hovering=false; refreshAppearance()}
    func refreshAppearance() {
        wantsLayer=true
        let orange=NSColor(srgbRed:1,green:0.36,blue:0.12,alpha:1)
        let active=hovering && isEnabled
        layer?.cornerRadius=9
        layer?.backgroundColor=(active ? orange.withAlphaComponent(0.22) : primary ? orange.withAlphaComponent(0.12) : NSColor.white.withAlphaComponent(0.045)).cgColor
        layer?.borderWidth=active || primary ? 1 : 0
        layer?.borderColor=orange.withAlphaComponent(active ? 0.85 : 0.4).cgColor
        contentTintColor=active || primary ? orange : .labelColor
        alphaValue=isEnabled ? 1 : 0.38
    }
}

final class FlippedView: NSView { override var isFlipped: Bool { true } }

final class App: NSObject, NSApplicationDelegate, NSWindowDelegate, NSTextViewDelegate, NSMenuItemValidation {
    var window: NSWindow!
    let photo = NSTextField(), audio = NSTextField(), logo = NSTextField()
    let photosFolder = NSTextField()
    let batchStatus = NSTextField(labelWithString:"Одиночный сценарий")
    var batchItems = [[String:Any]]()
    let transcript = NSTextField()
    let theme = NSPopUpButton(), accent = NSColorWell(), headline = NSTextField()
    let editor = NSTextView(), log = NSTextView()
    let scriptCount = NSTextField(labelWithString: "")
    let status = NSTextField(labelWithString: "Готов к работе")
    let create = IconButton(title: "Создать видео", target: nil, action: nil)
    let cancel = IconButton(title: "Остановить", target: nil, action: nil)
    let result = IconButton(title: "Открыть результат", target: nil, action: nil)
    let voiceOnly = NSButton(checkboxWithTitle: "Только голос — проверить речь перед видео", target: nil, action: nil)
    let avatarStatus = NSTextField(wrappingLabelWithString: "Аватар ещё не подключён")
    let avatarName = NSTextField()
    let setup = NSStackView()
    var preparedPlan: [String:Any]?
    var preparedSource = ""
    let uploadToDrive = NSButton(checkboxWithTitle:"Google Drive — загрузить готовый результат",target:nil,action:nil)
    var sourcePrompt = ""
    var historyItems = [[String:Any]]()
    let historyChoice = NSPopUpButton()
    let historySearch = NSSearchField()
    let historyDetail = NSTextView()
    var avatarFolder: URL?
    let orange = NSColor(srgbRed:1, green:0.36, blue:0.12, alpha:1)
    var process: Process?, timer: Timer?, job: URL?, output: URL?
    var root: URL {
        let path = Bundle.main.object(forInfoDictionaryKey: "AvatarProjectRoot") as? String ?? ""
        return URL(fileURLWithPath: path)
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x:0,y:0,width:980,height:920), styleMask:[.titled,.closable,.miniaturizable,.resizable], backing:.buffered, defer:false)
        window.title = "Аватар Студия · " + (Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "dev"); window.delegate = self; window.minSize = NSSize(width:800,height:650)
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = NSColor(srgbRed:0.075,green:0.08,blue:0.095,alpha:1)
        let page = NSScrollView(); page.hasVerticalScroller = true; page.translatesAutoresizingMaskIntoConstraints = false
        let menuStrip=NSView(); menuStrip.translatesAutoresizingMaskIntoConstraints=false
        menuStrip.wantsLayer=true; menuStrip.layer?.backgroundColor=NSColor(srgbRed:0.12,green:0.13,blue:0.15,alpha:1).cgColor
        let menuButtons=NSStackView(); menuButtons.orientation = .horizontal; menuButtons.spacing=4
        menuButtons.translatesAutoresizingMaskIntoConstraints=false; menuStrip.addSubview(menuButtons)
        let menuSymbols=["Аватар Студия":"sparkles.rectangle.stack", "Файл":"doc", "Правка":"pencil", "Аватар":"person.crop.circle", "Генерация":"play.rectangle", "Окно":"macwindow", "Справка":"questionmark.circle"]
        for title in ["Аватар Студия","Файл","Правка","Аватар","Генерация","Окно","Справка"] {
            let button=iconButton(title,menuSymbols[title]!,#selector(showInlineMenu(_:)))
            button.identifier=NSUserInterfaceItemIdentifier(title)
            button.refusesFirstResponder=true; button.toolTip="Меню «"+title+"»"
            menuButtons.addArrangedSubview(button)
        }
        window.contentView!.addSubview(menuStrip); window.contentView!.addSubview(page)
        NSLayoutConstraint.activate([
            menuStrip.leadingAnchor.constraint(equalTo:window.contentView!.leadingAnchor),
            menuStrip.trailingAnchor.constraint(equalTo:window.contentView!.trailingAnchor),
            menuStrip.topAnchor.constraint(equalTo:window.contentView!.topAnchor),menuStrip.heightAnchor.constraint(equalToConstant:52),
            menuButtons.leadingAnchor.constraint(equalTo:menuStrip.leadingAnchor,constant:16),
            menuButtons.centerYAnchor.constraint(equalTo:menuStrip.centerYAnchor),
            menuButtons.trailingAnchor.constraint(lessThanOrEqualTo:menuStrip.trailingAnchor,constant:-16),
            page.leadingAnchor.constraint(equalTo:window.contentView!.leadingAnchor),page.trailingAnchor.constraint(equalTo:window.contentView!.trailingAnchor),
            page.topAnchor.constraint(equalTo:menuStrip.bottomAnchor),page.bottomAnchor.constraint(equalTo:window.contentView!.bottomAnchor)])
        let document = FlippedView(); document.translatesAutoresizingMaskIntoConstraints = false; page.documentView = document
        document.addSubview(stack)
        document.widthAnchor.constraint(equalTo:page.contentView.widthAnchor).isActive = true
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo:document.leadingAnchor,constant:24),stack.trailingAnchor.constraint(equalTo:document.trailingAnchor,constant:-24),stack.topAnchor.constraint(equalTo:document.topAnchor,constant:24),stack.bottomAnchor.constraint(equalTo:document.bottomAnchor,constant:-24)])
        let eyebrow = label("AVATAR STUDIO     /     ЛОКАЛЬНО НА ВАШЕМ MAC")
        eyebrow.textColor = orange; eyebrow.font = .systemFont(ofSize:11,weight:.bold); stack.addArrangedSubview(eyebrow)
        let title = NSTextField(labelWithString:"Ваш аватар. Ваша история.")
        title.font = .systemFont(ofSize:30,weight:.bold); stack.addArrangedSubview(title)
        stack.addArrangedSubview(label("Подключите аватара, напишите сценарий и сначала проверьте голос."))
        let savePrompt=iconButton("Сохранить промпт · ⌘S","square.and.arrow.down",#selector(saveCurrentPrompt))
        let browse=iconButton("Промпты и генерации · ⌘L","clock.arrow.circlepath",#selector(showHistory))
        let library=NSStackView(views:[savePrompt,browse]); library.spacing=12; stack.addArrangedSubview(library)
        let avatarCard = section(stack,"01   ЦИФРОВОЙ АВАТАР")
        avatarStatus.font = .systemFont(ofSize:15,weight:.semibold); avatarCard.addArrangedSubview(avatarStatus)
        let newAvatar = iconButton("Создать аватара","person.crop.circle.badge.plus",#selector(newAvatar))
        let connect = iconButton("Подключить папку аватара · ⌘O","folder.badge.plus",#selector(connectAvatar))
        let buttons = NSStackView(views:[newAvatar,connect]); buttons.spacing=12; avatarCard.addArrangedSubview(buttons)
        avatarCard.addArrangedSubview(label("Профиль хранит портрет, образец голоса и расшифровку. Модели использует установленный движок студии."))
        setup.orientation = .vertical; setup.alignment = .leading; setup.spacing = 10
        avatarCard.addArrangedSubview(setup); setup.widthAnchor.constraint(equalTo:avatarCard.widthAnchor).isActive=true
        avatarName.placeholderString = "Имя аватара"; setup.addArrangedSubview(avatarName)
        avatarName.widthAnchor.constraint(equalTo:setup.widthAnchor).isActive=true
        setup.addArrangedSubview(label("1. Назовите аватара и выберите чёткий портрет. Для плана за столом оставьте в кадре верх тела, чашку и ноутбук."))
        addPicker(setup,"Выбрать портрет",photo,#selector(pickPhoto))
        setup.addArrangedSubview(label("2. Запишите 2–30 секунд чистой речи в Диктофоне, экспортируйте запись и выберите её здесь. Без музыки и посторонних голосов."))
        let recorder = iconButton("Открыть Диктофон","mic",#selector(openRecorder)); setup.addArrangedSubview(recorder)
        addPicker(setup,"Образец голоса",audio,#selector(pickAudio))
        setup.addArrangedSubview(label("3. Введите точные слова из записи. Сохраните профиль в новую папку — затем его можно подключить одним действием."))
        transcript.placeholderString = "Точный текст записи голоса"
        setup.addArrangedSubview(transcript); transcript.widthAnchor.constraint(equalTo:setup.widthAnchor).isActive=true
        let save = iconButton("Сохранить и подключить аватара","checkmark.circle",#selector(saveAvatar)); setup.addArrangedSubview(save)
        addPicker(stack,"Логотип (опционально)",logo,#selector(pickLogo))
        addPicker(stack,"Папка случайных фото (опционально)",photosFolder,#selector(pickPhotosFolder))
        stack.addArrangedSubview(label("Одно случайное фото на ролик; голос берётся из профиля. Используйте фото одного человека. Пустое поле — портрет профиля."))
        stack.addArrangedSubview(label("Голос: ESpeech · естественный темп 1.0 · проверка ударений и пауз до видео."))
        sectionTitle(stack,"02   СЦЕНАРИЙ И ОФОРМЛЕНИЕ")
        stack.addArrangedSubview(label("Видео с мимикой: перенос движений пока не поддерживается. Движения создаёт LTX."))
        stack.addArrangedSubview(label("Сценарий · вставьте полное задание со сценами и репликами Озвучка: «…». Сначала подготовьте план; до 1500 символов готовой речи / 90 секунд."))
        editor.textColor = .labelColor; editor.insertionPointColor = orange; editor.textContainerInset = NSSize(width:14,height:12); editor.isRichText = false; editor.font = .systemFont(ofSize:15); editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.string = "Поднял кластер ради двух контейнеров?\nKubernetes — не бесплатная масштабируемость.\nСначала назови проблему, которую Kubernetes должен решить."
        sourcePrompt=(try? String(contentsOf:root.appendingPathComponent("mac-app/jobs/source-prompt-draft.txt"),encoding:.utf8)) ?? ""
        editor.delegate=self
        if let draft=try? String(contentsOf:root.appendingPathComponent("mac-app/jobs/speech-draft.txt"),encoding:.utf8) { editor.string=draft }
        addScroll(stack,editor,180)
        let extract=iconButton("Подготовить сценарий и посмотреть план","list.bullet.rectangle",#selector(extractSpeech))
        let scriptTools=NSStackView(views:[extract,scriptCount]); scriptTools.spacing=12; stack.addArrangedSubview(scriptTools)
        updateScriptCount()
        let importList = NSButton(title:"Загрузить список сценариев…",target:self,action:#selector(importBatch))
        let clearList = NSButton(title:"Одиночный режим",target:self,action:#selector(clearBatch))
        let resumeList = NSButton(title:"Продолжить очередь…",target:self,action:#selector(resumeBatch))
        let batchRow = NSStackView(views:[importList,clearList,resumeList]); batchRow.spacing=10
        stack.addArrangedSubview(batchRow); stack.addArrangedSubview(batchStatus)
        stack.addArrangedSubview(label("JSON: список title/script; CSV: title,script; TXT: один сценарий в файле. Можно выбрать несколько файлов. Очередь выполняется последовательно; ошибка ставит её на паузу."))
        theme.addItems(withTitles:["Тёмный техно","Светлый редакционный","Контрастный"])
        theme.target=self; theme.action=#selector(themeChanged)
        accent.color=orange
        accent.widthAnchor.constraint(equalToConstant:60).isActive=true
        let designRow=NSStackView(views:[label("Оформление"),theme,label("Акцент"),accent]); designRow.spacing=12
        stack.addArrangedSubview(designRow)
        headline.placeholderString="Заголовок первых 3 секунд (необязательно, до 90 символов)"
        stack.addArrangedSubview(headline); headline.widthAnchor.constraint(equalTo:stack.widthAnchor).isActive=true
        voiceOnly.target=self; voiceOnly.action=#selector(modeChanged)
        stack.addArrangedSubview(voiceOnly)
        let driveSettings=iconButton("Настроить Google Drive","externaldrive.badge.icloud",#selector(configureDrive))
        let driveRow=NSStackView(views:[uploadToDrive,driveSettings]);driveRow.spacing=10;stack.addArrangedSubview(driveRow)
        stack.addArrangedSubview(label("Видео: 720 × 1280 · герой, схемы и анимированные карточки · длительность по реальной речи."))
        let actions = NSStackView(views:[create,cancel,result]); actions.spacing = 12
        create.target = self; create.action = #selector(start); create.bezelStyle = .rounded
        cancel.target = self; cancel.action = #selector(stop); cancel.isEnabled = false
        result.target = self; result.action = #selector(openResult); result.isEnabled = false
        decorateIcon(create,"Создать видео","video.badge.plus"); create.primary=true
        decorateIcon(cancel,"Остановить генерацию · ⌘.","stop.fill")
        decorateIcon(result,"Открыть результат","arrow.up.right.square")
        sectionTitle(stack,"03   ГЕНЕРАЦИЯ")
        stack.addArrangedSubview(actions); stack.addArrangedSubview(status)
        log.isEditable = false; log.isRichText = false; log.font = .monospacedSystemFont(ofSize:11,weight:.regular)
        addScroll(stack,log,140)
        stack.addArrangedSubview(label("Проекты: mac-app/jobs · исходники и предыдущие результаты сохраняются."))
        installMenus()
        editor.allowsUndo=true
        if let icon=Bundle.main.url(forResource:"AvatarStudio",withExtension:"icns") {NSApp.applicationIconImage=NSImage(contentsOf:icon)}
        if let path = UserDefaults.standard.string(forKey:"avatarFolder") {
            do { try loadAvatar(URL(fileURLWithPath:path)) }
            catch { avatarStatus.stringValue = "Профиль недоступен. Подключите папку заново или создайте аватара." }
        }
        window.center(); window.makeKeyAndOrderFront(nil); page.contentView.scroll(to:.zero); page.reflectScrolledClipView(page.contentView); NSApp.activate(ignoringOtherApps:true)
    }
    func decorateIcon(_ button:IconButton,_ title:String,_ symbol:String) {
        button.title=""; button.toolTip=title; button.setAccessibilityLabel(title)
        button.image=NSImage(systemSymbolName:symbol,accessibilityDescription:title)?.withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize:19,weight:.medium)) ?? NSImage(systemSymbolName:"questionmark.circle",accessibilityDescription:title)
        button.imagePosition = .imageOnly; button.imageScaling = .scaleProportionallyDown
        button.isBordered=false; button.bezelStyle = .regularSquare
        button.widthAnchor.constraint(equalToConstant:38).isActive=true
        button.heightAnchor.constraint(equalToConstant:36).isActive=true
        button.refreshAppearance()
    }
    func iconButton(_ title:String,_ symbol:String,_ action:Selector)->IconButton {
        let button=IconButton(title:"",target:self,action:action)
        decorateIcon(button,title,symbol); return button
    }
    @objc func showInlineMenu(_ sender:NSButton) {
        guard let title=sender.identifier?.rawValue,
              let original=NSApp.mainMenu?.items.first(where:{$0.title == title})?.submenu,
              let menu=original.copy() as? NSMenu else {return}
        window.makeKeyAndOrderFront(nil)
        for item in menu.items {
            if item.action == #selector(NSWindow.performClose(_:)) || item.action == #selector(NSWindow.performMiniaturize(_:)) || item.action == #selector(NSWindow.performZoom(_:)) {item.target=window}
        }
        menu.popUp(positioning:nil,at:NSPoint(x:0,y:sender.bounds.minY-sender.bounds.height-12),in:sender)
    }
    func installMenus() {
        let bar=NSMenu()
        func group(_ title:String)->NSMenu {
            let item=NSMenuItem(title:title,action:nil,keyEquivalent:""); let menu=NSMenu(title:title)
            item.submenu=menu; bar.addItem(item); return menu
        }
        @discardableResult func command(_ menu:NSMenu,_ title:String,_ action:Selector,_ key:String="",_ modifiers:NSEvent.ModifierFlags = .command,_ target:AnyObject?=nil)->NSMenuItem {
            let item=NSMenuItem(title:title,action:action,keyEquivalent:key)
            item.keyEquivalentModifierMask=modifiers; item.target=target; menu.addItem(item); return item
        }
        let appMenu=group("Аватар Студия")
        command(appMenu,"Об Аватар Студии",#selector(showAbout),"",.command,self)
        appMenu.addItem(.separator())
        let services=NSMenu(title:"Службы"); let servicesItem=NSMenuItem(title:"Службы",action:nil,keyEquivalent:""); servicesItem.submenu=services; appMenu.addItem(servicesItem); NSApp.servicesMenu=services
        appMenu.addItem(.separator())
        command(appMenu,"Скрыть Аватар Студию",#selector(NSApplication.hide(_:)),"h")
        command(appMenu,"Скрыть остальные",#selector(NSApplication.hideOtherApplications(_:)),"h",[.command,.option])
        command(appMenu,"Показать все",#selector(NSApplication.unhideAllApplications(_:)))
        appMenu.addItem(.separator()); command(appMenu,"Завершить Аватар Студию",#selector(NSApplication.terminate(_:)),"q")
        let file=group("Файл")
        command(file,"Сохранить промпт",#selector(saveCurrentPrompt),"s",.command,self)
        command(file,"Промпты и генерации…",#selector(showHistory),"l",.command,self)
        command(file,"Показать папку генераций",#selector(showJobs),"",.command,self)
        command(file,"Настроить Google Drive…",#selector(configureDrive),"",.command,self)
        file.addItem(.separator()); command(file,"Закрыть окно",#selector(NSWindow.performClose(_:)),"w")
        let edit=group("Правка")
        command(edit,"Отменить",Selector(("undo:")),"z")
        command(edit,"Повторить",Selector(("redo:")),"z",[.command,.shift])
        edit.addItem(.separator())
        command(edit,"Вырезать",#selector(NSText.cut(_:)),"x")
        command(edit,"Копировать",#selector(NSText.copy(_:)),"c")
        command(edit,"Вставить",#selector(NSText.paste(_:)),"v")
        command(edit,"Выделить всё",#selector(NSText.selectAll(_:)),"a")
        edit.addItem(.separator()); command(edit,"Подготовить сценарий…",#selector(extractSpeech),"e",[.command,.shift],self)
        let avatar=group("Аватар")
        command(avatar,"Создать аватара…",#selector(newAvatar),"n",[.command,.shift],self)
        command(avatar,"Подключить папку…",#selector(connectAvatar),"o",.command,self)
        command(avatar,"Открыть Диктофон",#selector(openRecorder),"",.command,self)
        let generation=group("Генерация")
        command(generation,"Создать голос",#selector(startVoice),"g",.command,self)
        command(generation,"Создать видео",#selector(startVideo),"g",[.command,.shift],self)
        generation.addItem(.separator())
        command(generation,"Остановить",#selector(stop),".",.command,self)
        command(generation,"Показать результат",#selector(openResult),"r",[.command,.shift],self)
        let windows=group("Окно"); NSApp.windowsMenu=windows
        command(windows,"Свернуть",#selector(NSWindow.performMiniaturize(_:)),"m")
        command(windows,"Изменить масштаб",#selector(NSWindow.performZoom(_:)))
        command(windows,"Все окна на передний план",#selector(NSApplication.arrangeInFront(_:)))
        let help=group("Справка"); NSApp.helpMenu=help
        command(help,"Как создать первый ролик",#selector(showGuide),"?",.command,self)
        NSApp.mainMenu=bar
    }
    func validateMenuItem(_ item:NSMenuItem)->Bool {
        switch item.action {
        case #selector(startVoice), #selector(startVideo): return process == nil && avatarFolder != nil && (!batchItems.isEmpty || !editor.string.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
        case #selector(stop): return process != nil && cancel.isEnabled
        case #selector(openResult): return output != nil && result.isEnabled
        case #selector(newAvatar), #selector(connectAvatar): return process == nil
        case #selector(extractSpeech): return process == nil && !editor.string.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty
        case #selector(saveCurrentPrompt): return !editor.string.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty
        default: return true
        }
    }
    @objc func startVoice() {guard process == nil else{return}; voiceOnly.state = .on; modeChanged(); start()}
    @objc func startVideo() {guard process == nil else{return}; voiceOnly.state = .off; modeChanged(); start()}
    @objc func showJobs() {
        let folder=root.appendingPathComponent("mac-app/jobs")
        do {try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true); NSWorkspace.shared.open(folder)}
        catch {alert(error.localizedDescription)}
    }
    @objc func showAbout() {NSApp.orderFrontStandardAboutPanel(options:[.applicationName:"Аватар Студия",.applicationVersion:Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "",.credits:NSAttributedString(string:"Локальная студия цифрового аватара\nФото · голос · сценарий → видео")])}
    @objc func showGuide() {alert("1. Аватар → Создать аватара или Подключить папку.\n2. Вставьте полный сценарий. Затем: Правка → Подготовить сценарий.\n3. Генерация → Создать голос. Прослушайте результат.\n4. Генерация → Создать видео.\n5. Файл → Промпты и генерации — ваша библиотека.\n\nПри работающей генерации сначала используйте Генерация → Остановить (⌘.).")}
    func historyCall(_ action:String, extra:[String]=[], payload:[String:String]?=nil, script:String="history.py") throws -> [String:Any] {
        let worker=Process(); worker.executableURL=URL(fileURLWithPath:"/usr/bin/python3")
        worker.arguments=[root.appendingPathComponent("mac-app/engine/"+script).path,action]+extra
        let out=Pipe(), errors=Pipe(); worker.standardOutput=out; worker.standardError=errors
        let input=Pipe(); worker.standardInput=input
        try worker.run()
        if let payload=payload {input.fileHandleForWriting.write(try JSONSerialization.data(withJSONObject:payload))}
        try input.fileHandleForWriting.close()
        let data=out.fileHandleForReading.readDataToEndOfFile()
        let errorData=errors.fileHandleForReading.readDataToEndOfFile(); worker.waitUntilExit()
        guard worker.terminationStatus == 0 else {throw NSError(domain:"History",code:1,userInfo:[NSLocalizedDescriptionKey:String(data:errorData,encoding:.utf8) ?? "Ошибка базы истории"])}
        return (try? JSONSerialization.jsonObject(with:data)) as? [String:Any] ?? [:]
    }
    @objc func saveCurrentPrompt() {
        do {
            _ = try historyCall("save",payload:["source":editor.string,"speech":preparedPlan?["speech"] as? String ?? ScriptInput.speech(editor.string) ?? editor.string])
            status.stringValue="Промпт сохранён в локальной библиотеке."
        } catch {alert(error.localizedDescription)}
    }
    @objc func reloadHistory() {
        do {
            let response=try historyCall("list",extra:["--query",historySearch.stringValue])
            historyItems=response["items"] as? [[String:Any]] ?? []
            historyChoice.removeAllItems()
            for (index,item) in historyItems.enumerated() {
                let formatter=ISO8601DateFormatter(); formatter.formatOptions=[.withInternetDateTime,.withFractionalSeconds]
                let date=(item["created"] as? String).flatMap { formatter.date(from:$0) }
                let formatted=date.map {DateFormatter.localizedString(from:$0,dateStyle:.short,timeStyle:.short)} ?? String((item["created"] as? String ?? "").prefix(16))
                historyChoice.addItem(withTitle:"\(index+1). \(formatted) · \(item["stage"] as? String ?? "") · \(item["title"] as? String ?? "")")
            }
            if historyItems.isEmpty {historyChoice.addItem(withTitle:"Записей не найдено")}
            historySelected()
            if let warnings=response["warnings"] as? [String], !warnings.isEmpty {historyDetail.string += "\n\nНе импортированы:\n"+warnings.joined(separator:"\n")}
        } catch {historyItems=[]; historyChoice.removeAllItems(); historyDetail.string=error.localizedDescription}
    }
    @objc func historySelected() {
        let index=historyChoice.indexOfSelectedItem
        guard historyItems.indices.contains(index) else {historyDetail.string="Сохраните промпт или создайте генерацию.";return}
        let item=historyItems[index]
        historyDetail.string="ИСХОДНЫЙ ПРОМПТ\n"+(item["source"] as? String ?? "")+"\n\nОЗВУЧКА\n"+(item["speech"] as? String ?? "")+"\n\nСТАТУС\n"+(item["message"] as? String ?? item["stage"] as? String ?? "")+"\n\nРЕЗУЛЬТАТ\n"+(item["output"] as? String ?? "")
        if let config=item["config"], let data=try? JSONSerialization.data(withJSONObject:config,options:[.prettyPrinted,.sortedKeys]), let text=String(data:data,encoding:.utf8) {historyDetail.string += "\n\nНАСТРОЙКИ\n"+text}
    }
    @objc func showHistory() {
        let dialog=NSAlert(); dialog.messageText="Промпты и генерации"
        dialog.informativeText="Локальная SQLite-база. Поиск — введите текст и нажмите Return. Использование записи заменит текущий сценарий; настройки аватара остаются выбранными."
        dialog.addButton(withTitle:"Закрыть"); dialog.addButton(withTitle:"Использовать сценарий"); dialog.addButton(withTitle:"Показать файлы")
        let content=NSStackView(); content.orientation = .vertical; content.alignment = .leading; content.spacing=10
        content.frame=NSRect(x:0,y:0,width:680,height:420)
        historySearch.placeholderString="Поиск по тексту, статусу и настройкам"; historySearch.target=self; historySearch.action=#selector(reloadHistory)
        historyChoice.target=self; historyChoice.action=#selector(historySelected)
        content.addArrangedSubview(historySearch); content.addArrangedSubview(historyChoice)
        historySearch.widthAnchor.constraint(equalToConstant:680).isActive=true; historyChoice.widthAnchor.constraint(equalToConstant:680).isActive=true
        historyDetail.isEditable=false; historyDetail.isRichText=false; historyDetail.font = .systemFont(ofSize:12)
        addScroll(content,historyDetail,340); dialog.accessoryView=content
        reloadHistory()
        let response=dialog.runModal(); let index=historyChoice.indexOfSelectedItem
        guard historyItems.indices.contains(index) else{return}; let item=historyItems[index]
        if response == .alertSecondButtonReturn {
            guard process == nil else {alert("Дождитесь завершения генерации.");return}
            do {
                try editor.string.write(to:root.appendingPathComponent("mac-app/jobs/script-before-history-"+UUID().uuidString+".txt"),atomically:true,encoding:.utf8)
                sourcePrompt=item["source"] as? String ?? ""; editor.string=(item["source"] as? String).flatMap {$0.isEmpty ? nil : $0} ?? item["speech"] as? String ?? ""
                textDidChange(Notification(name:NSText.didChangeNotification))
            } catch {alert(error.localizedDescription)}
        } else if response == .alertThirdButtonReturn {
            let output=item["output"] as? String ?? ""; let folder=item["job"] as? String ?? ""
            let path=FileManager.default.fileExists(atPath:output) ? output : folder
            if !path.isEmpty, FileManager.default.fileExists(atPath:path) {NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath:path)])}
            else {alert("У этой записи нет доступных файлов результата.")}
        }
    }
    func updateScriptCount() {
        if let plan=preparedPlan, preparedSource==editor.string {
            scriptCount.stringValue="\((plan["scenes"] as? [Any])?.count ?? 0) сцен · \((plan["speech"] as? String ?? "").unicodeScalars.count) / 1500 символов речи · план готов"
            scriptCount.textColor = .secondaryLabelColor
        } else {
            scriptCount.stringValue="\(editor.string.unicodeScalars.count) символов сценария · подготовьте план"
            scriptCount.textColor=orange
        }
    }
    func textDidChange(_ notification:Notification) {
        preparedPlan=nil; preparedSource=""; updateScriptCount()
        try? editor.string.write(to:root.appendingPathComponent("mac-app/jobs/speech-draft.txt"),atomically:true,encoding:.utf8)
        try? sourcePrompt.write(to:root.appendingPathComponent("mac-app/jobs/source-prompt-draft.txt"),atomically:true,encoding:.utf8)
    }
    @objc func extractSpeech() {
        guard process == nil else{return}
        do {
            let plan=try historyCall("prepare",payload:["source":editor.string,"title":headline.stringValue],script:"scenario.py")
            let scenes=plan["scenes"] as? [[String:Any]] ?? []
            let warnings=plan["warnings"] as? [String] ?? []
            let description=scenes.map { row in
                "СЦЕНА \(row["id"] ?? "") · \(row["kind"] as? String == "hero" ? "ГЕРОЙ" : "ГРАФИКА") · \(["statement":"карточки","comparison":"сравнение","diagram":"схема","checklist":"чек-лист"][row["style"] as? String ?? ""] ?? "карточки")\nНадпись: \(row["headline"] as? String ?? "")\nОзвучка: \(row["speech"] as? String ?? "")"
            }.joined(separator:"\n\n")+"\n\nПРИМЕЧАНИЯ\n"+warnings.joined(separator:"\n")
            let dialog=NSAlert(); dialog.messageText="План ролика";dialog.informativeText="Проверьте сцены и речь. Таймкоды будут рассчитаны после озвучки. Исходный сценарий останется в редакторе."
            dialog.addButton(withTitle:"Применить план");dialog.addButton(withTitle:"Вернуться к сценарию")
            let scroll=NSScrollView(frame:NSRect(x:0,y:0,width:680,height:420));scroll.hasVerticalScroller=true
            let preview=NSTextView(frame:scroll.bounds);preview.isEditable=false;preview.isRichText=false;preview.font = .systemFont(ofSize:13)
            preview.string=description;preview.isVerticallyResizable=true;preview.autoresizingMask=[.width];preview.textContainer?.widthTracksTextView=true;scroll.documentView=preview;dialog.accessoryView=scroll
            guard dialog.runModal() == .alertFirstButtonReturn else{return}
            _ = try historyCall("save",payload:["source":editor.string,"speech":plan["speech"] as? String ?? "","title":plan["title"] as? String ?? ""])
            preparedPlan=plan;preparedSource=editor.string;sourcePrompt=editor.string
            if headline.stringValue.isEmpty {headline.stringValue=plan["title"] as? String ?? ""}
            updateScriptCount();status.stringValue="План подготовлен и сохранён. Можно создать голос или видео."
        } catch {alert(error.localizedDescription)}
    }
    @objc func configureDrive() {
        let dialog=NSAlert();dialog.messageText="Google Drive";dialog.informativeText="Сначала в Терминале: brew install rclone, затем rclone config (remote gdrive, Google Drive). После авторизации сохраните папку назначения здесь. По SSH настройка описана в mac-app/CLI.md."
        let field=NSTextField(frame:NSRect(x:0,y:0,width:420,height:26));field.stringValue="gdrive:AvatarStudio";dialog.accessoryView=field
        dialog.addButton(withTitle:"Сохранить назначение");dialog.addButton(withTitle:"Отмена")
        guard dialog.runModal() == .alertFirstButtonReturn else{return}
        do {_ = try historyCall("drive-setup",extra:["--destination",field.stringValue],script:"studio_cli.py");status.stringValue="Назначение Google Drive сохранено."}
        catch {alert(error.localizedDescription)}
    }
    func sectionTitle(_ stack:NSStackView,_ title:String) {
        let heading=label(title); heading.textColor=orange; heading.font = .systemFont(ofSize:11,weight:.bold)
        stack.addArrangedSubview(heading)
    }
    func section(_ parent:NSStackView,_ title:String)->NSStackView {
        let box=NSBox(); box.title=""; box.boxType = .custom; box.borderWidth = 0
        box.fillColor=NSColor(srgbRed:0.12,green:0.13,blue:0.15,alpha:1); box.cornerRadius=14
        let content=NSStackView(); content.orientation = .vertical; content.alignment = .leading; content.spacing=10
        content.translatesAutoresizingMaskIntoConstraints=false; box.contentView=NSView(); box.contentView!.addSubview(content)
        NSLayoutConstraint.activate([content.leadingAnchor.constraint(equalTo:box.contentView!.leadingAnchor,constant:16),content.trailingAnchor.constraint(equalTo:box.contentView!.trailingAnchor,constant:-16),content.topAnchor.constraint(equalTo:box.contentView!.topAnchor,constant:16),content.bottomAnchor.constraint(equalTo:box.contentView!.bottomAnchor,constant:-16)])
        parent.addArrangedSubview(box); box.widthAnchor.constraint(equalTo:parent.widthAnchor).isActive=true
        sectionTitle(content,title); return content
    }
    @objc func newAvatar() {
        guard process == nil else { alert("Дождитесь завершения генерации."); return }
        avatarFolder=nil; photo.stringValue=""; audio.stringValue=""; transcript.stringValue=""; avatarName.stringValue=""
        UserDefaults.standard.removeObject(forKey:"avatarFolder")
        setup.isHidden=false; avatarStatus.stringValue="Создайте аватара за три шага"; window.makeFirstResponder(avatarName)
    }
    @objc func openRecorder() {
        if let url=NSWorkspace.shared.urlForApplication(withBundleIdentifier:"com.apple.VoiceMemos") {
            NSWorkspace.shared.openApplication(at:url,configuration:NSWorkspace.OpenConfiguration())
        } else { alert("Откройте приложение для записи звука и экспортируйте запись в WAV, M4A или MP3.") }
    }
    @objc func connectAvatar() {
        guard process == nil else { alert("Дождитесь завершения генерации."); return }
        let panel=NSOpenPanel(); panel.canChooseFiles=false; panel.canChooseDirectories=true; panel.allowsMultipleSelection=false
        panel.message="Выберите папку с avatar.json. Для старой папки без профиля будет доступна подготовка вручную."
        guard panel.runModal() == .OK, let dir=panel.url else {return}
        do {try loadAvatar(dir)} catch {alert("Не удалось подключить профиль: " + error.localizedDescription + "\nЕсли это старая папка с медиа, нажмите «Создать аватара», выберите из неё портрет и голос, затем сохраните профиль в новую папку.")}
    }
    func loadAvatar(_ dir:URL) throws {
        let profile=try JSONDecoder().decode(AvatarProfile.self,from:Data(contentsOf:dir.appendingPathComponent("avatar.json")))
        let portrait=dir.appendingPathComponent(profile.photo).standardizedFileURL
        let voice=dir.appendingPathComponent(profile.audio).standardizedFileURL
        guard profile.version == 1, !profile.name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              !profile.text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              NSImage(contentsOf:portrait) != nil, FileManager.default.isReadableFile(atPath:voice.path) else {
            throw NSError(domain:"Avatar",code:1,userInfo:[NSLocalizedDescriptionKey:"Проверьте версию профиля, портрет, аудиофайл и расшифровку."])
        }
        photo.stringValue=portrait.path; audio.stringValue=voice.path; transcript.stringValue=profile.text; avatarName.stringValue=profile.name
        avatarFolder=dir; setup.isHidden=true; avatarStatus.stringValue="●  " + profile.name + "  ·  аватар подключён"
        UserDefaults.standard.set(dir.path,forKey:"avatarFolder")
    }
    @objc func saveAvatar() {
        guard process == nil else {return}
        guard !avatarName.stringValue.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              !transcript.stringValue.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              NSImage(contentsOfFile:photo.stringValue) != nil, FileManager.default.isReadableFile(atPath:audio.stringValue) else {
            alert("Укажите имя, читаемый портрет, файл голоса и точную расшифровку."); return
        }
        let panel=NSSavePanel(); panel.title="Новая папка аватара"; panel.nameFieldStringValue="Мой аватар"; panel.canCreateDirectories=true
        guard panel.runModal() == .OK, let dir=panel.url else{return}
        do {
            guard !FileManager.default.fileExists(atPath:dir.path) else {alert("Выберите новое имя папки. Существующие файлы не перезаписываются."); return}
            try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
            let portrait="portrait." + URL(fileURLWithPath:photo.stringValue).pathExtension
            let voice="voice." + URL(fileURLWithPath:audio.stringValue).pathExtension
            try FileManager.default.copyItem(at:URL(fileURLWithPath:photo.stringValue),to:dir.appendingPathComponent(portrait))
            try FileManager.default.copyItem(at:URL(fileURLWithPath:audio.stringValue),to:dir.appendingPathComponent(voice))
            let profile=AvatarProfile(version:1,name:avatarName.stringValue,photo:portrait,audio:voice,text:transcript.stringValue)
            try JSONEncoder().encode(profile).write(to:dir.appendingPathComponent("avatar.json"),options:.atomic)
            try loadAvatar(dir)
        } catch {alert("Не удалось сохранить профиль: " + error.localizedDescription)}
    }
    func label(_ text:String)->NSTextField { let v=NSTextField(wrappingLabelWithString:text); v.font = .systemFont(ofSize:12); v.textColor = .secondaryLabelColor; return v }
    func addPicker(_ stack:NSStackView,_ title:String,_ field:NSTextField,_ action:Selector) {
        let symbol = action == #selector(pickAudio) ? "waveform" : action == #selector(pickLogo) ? "seal" : "photo"
        let button = iconButton(title+"…",symbol,action)
        field.placeholderString = title+" — выберите файл"; field.isEditable = true; field.lineBreakMode = .byTruncatingMiddle
        let row = NSStackView(views:[button,field]); row.spacing=10; stack.addArrangedSubview(row); row.widthAnchor.constraint(equalTo:stack.widthAnchor).isActive=true
    }
    func addScroll(_ stack:NSStackView,_ text:NSTextView,_ height:CGFloat) {
        let scroll=NSScrollView(); scroll.hasVerticalScroller=true; scroll.borderType = .bezelBorder; scroll.documentView=text
        text.autoresizingMask=[.width]; text.isVerticallyResizable=true; text.isHorizontallyResizable=false
        text.textContainer?.widthTracksTextView=true
        stack.addArrangedSubview(scroll); scroll.widthAnchor.constraint(equalTo:stack.widthAnchor).isActive=true; scroll.heightAnchor.constraint(greaterThanOrEqualToConstant:height).isActive=true
    }
    @discardableResult func choose(_ field:NSTextField)->Bool { let p=NSOpenPanel(); p.canChooseDirectories=false; p.allowsMultipleSelection=false; if p.runModal() == .OK { field.stringValue=p.url!.path; return true }; return false }
    @objc func modeChanged() {
        let title=voiceOnly.state == .on ? "Создать голос · ⌘G" : "Создать видео · ⌘⇧G"
        create.title=""; create.toolTip=title; create.setAccessibilityLabel(title)
        create.image=NSImage(systemSymbolName:voiceOnly.state == .on ? "waveform.badge.plus" : "video.badge.plus",accessibilityDescription:title)?.withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize:19,weight:.medium))
    }
    @objc func themeChanged() {
        let colors=["FF5C1F","245BDB","F5E642"]; let value=Int(colors[theme.indexOfSelectedItem],radix:16)!
        accent.color=NSColor(srgbRed:Double((value>>16)&255)/255,green:Double((value>>8)&255)/255,blue:Double(value&255)/255,alpha:1)
    }
    func designConfig()->[String:String] {
        let color=accent.color.usingColorSpace(.sRGB) ?? .cyan
        let hex=String(format:"#%02X%02X%02X",Int(color.redComponent*255),Int(color.greenComponent*255),Int(color.blueComponent*255))
        return ["theme":["dark-tech","light-editorial","high-contrast"][theme.indexOfSelectedItem],"accent":hex,"headline":String(headline.stringValue.prefix(90))]
    }
    @objc func pickPhotosFolder() {
        let panel=NSOpenPanel(); panel.canChooseDirectories=true; panel.canChooseFiles=false
        if panel.runModal() == .OK, let url=panel.url {photosFolder.stringValue=url.path}
    }
    @objc func importBatch() {
        guard process == nil else{return}
        let panel=NSOpenPanel(); panel.allowsMultipleSelection=true; panel.allowedContentTypes=[.json,.commaSeparatedText,.plainText]
        if panel.runModal() != .OK {return}
        do {
            let response=try historyCall("inspect",extra:panel.urls.map{$0.path},script:"batch.py")
            let items=response["items"] as? [[String:Any]] ?? []
            guard !items.isEmpty else {alert("Список пуст");return}
            let preview=items.enumerated().map {"\($0.offset+1). \($0.element["title"] as? String ?? "Без названия")"}.joined(separator:"\n")
            let dialog=NSAlert(); dialog.messageText="Загрузить \(items.count) сценариев?"; dialog.informativeText=preview
            dialog.addButton(withTitle:"Загрузить список"); dialog.addButton(withTitle:"Отмена")
            if dialog.runModal() == .alertFirstButtonReturn {
                batchItems=items; batchStatus.stringValue="В очереди: \(items.count). Будут использованы сценарии из списка; редактор ниже — одиночный режим."
            }
        } catch {alert(error.localizedDescription)}
    }
    @objc func clearBatch() {guard process == nil else{return}; batchItems=[]; batchStatus.stringValue="Одиночный сценарий"}
    func launchQueue(_ dir:URL, arguments:[String]) throws {
        let p=Process(); p.executableURL=root.appendingPathComponent("local-avatar/.venv-lipsync/bin/python")
        p.arguments=["-u",root.appendingPathComponent("mac-app/engine/batch.py").path]+arguments
        var env=ProcessInfo.processInfo.environment; env["PATH"]="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"; p.environment=env
        p.currentDirectoryURL=root
        let file=dir.appendingPathComponent("run.log"); if !FileManager.default.fileExists(atPath:file.path) {FileManager.default.createFile(atPath:file.path,contents:nil)}
        let handle=try FileHandle(forWritingTo:file); try handle.seekToEnd(); p.standardOutput=handle; p.standardError=handle
        defer {try? handle.close()}; try p.run()
        process=p; job=dir; output=nil; create.isEnabled=false; cancel.isEnabled=true; result.isEnabled=false; status.stringValue="Очередь запускается…"
        timer=Timer.scheduledTimer(withTimeInterval:1,repeats:true){[weak self] _ in self?.refresh()}
    }
    @objc func resumeBatch() {
        guard process == nil else{return}
        let panel=NSOpenPanel(); panel.canChooseDirectories=true; panel.canChooseFiles=false
        panel.directoryURL=root.appendingPathComponent("mac-app/jobs")
        if panel.runModal() == .OK, let dir=panel.url {
            do {try launchQueue(dir,arguments:["run",dir.path])} catch {alert(error.localizedDescription)}
        }
    }
    func startBatch() {
        guard avatarFolder != nil, !transcript.stringValue.isEmpty else {alert("Подключите профиль с образцом и текстом голоса.");return}
        do {
            let dir=root.appendingPathComponent("mac-app/jobs/batch-"+UUID().uuidString)
            try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
            var config:[String:Any] = ["photo":photo.stringValue,"reference_audio":audio.stringValue,"reference_text":transcript.stringValue,"logo":logo.stringValue,"voice_only":voiceOnly.state == .on,"design":designConfig()]
            if uploadToDrive.state == .on {
                let settings=try Data(contentsOf:root.appendingPathComponent("mac-app/data/integrations.json"))
                guard let object=try JSONSerialization.jsonObject(with:settings) as? [String:Any], let target=object["drive_destination"] as? String else {alert("Сначала настройте Google Drive.");return}
                config["upload_destination"]=target
            }
            let base=dir.appendingPathComponent("base.json"), items=dir.appendingPathComponent("items.json")
            try JSONSerialization.data(withJSONObject:config).write(to:base)
            try JSONSerialization.data(withJSONObject:batchItems).write(to:items)
            var args=["start","--controller",dir.path,"--base",base.path,"--items",items.path]
            if !photosFolder.stringValue.isEmpty {args += ["--photos",photosFolder.stringValue]}
            try launchQueue(dir,arguments:args)
        } catch {alert(error.localizedDescription)}
    }
    @objc func pickPhoto(){choose(photo)}
    @objc func pickAudio(){if choose(audio) { transcript.stringValue="" }}
    @objc func pickLogo(){choose(logo)}
    func alert(_ message:String){let a=NSAlert(); a.messageText=message; a.runModal()}
    @objc func start() {
        guard process == nil else{return}
        if !batchItems.isEmpty {startBatch();return}
        guard avatarFolder != nil else {alert("Сначала создайте и сохраните аватара или подключите его папку.");return}
        if preparedSource != editor.string || preparedPlan == nil {extractSpeech()}
        guard let plan=preparedPlan, preparedSource==editor.string else{return}
        if !photosFolder.stringValue.isEmpty {
            batchItems=[["source":editor.string,"title":headline.stringValue,"plan":plan]]
            startBatch(); batchItems=[]; return
        }
        let speech=plan["speech"] as? String ?? ""
        if let issue=ScriptInput.issue(speech) {alert(issue);return}
        guard !editor.string.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty, !transcript.stringValue.isEmpty else {alert("Нужны сценарий и точный текст образца голоса.");return}
        do {
            let id=ISO8601DateFormatter().string(from:Date()).replacingOccurrences(of:":",with:"-")+"-"+UUID().uuidString.prefix(6)
            let dir=root.appendingPathComponent("mac-app/jobs/"+id); try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
            var config:[String:Any] = ["photo":photo.stringValue,"reference_audio":audio.stringValue,"reference_text":transcript.stringValue,"logo":logo.stringValue,"script":speech,"scenario_plan":plan,"title":headline.stringValue,"source_prompt":editor.string,"voice_only":voiceOnly.state == .on,"design":designConfig()]
            if uploadToDrive.state == .on {
                let settingsURL=root.appendingPathComponent("mac-app/data/integrations.json")
                guard let data=try? Data(contentsOf:settingsURL),let settings=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],let target=settings["drive_destination"] as? String else {alert("Сначала настройте Google Drive через Файл → Настроить Google Drive.");return}
                config["upload_destination"]=target
            }
            let configURL=dir.appendingPathComponent("project.json"); try JSONSerialization.data(withJSONObject:config,options:[.prettyPrinted,.sortedKeys]).write(to:configURL)
            _ = try historyCall("record",extra:["--job",dir.path])
            let logURL=dir.appendingPathComponent("run.log"); FileManager.default.createFile(atPath:logURL.path,contents:nil)
            let handle=try FileHandle(forWritingTo:logURL)
            let p=Process(); p.executableURL=root.appendingPathComponent("local-avatar/.venv-lipsync/bin/python")
            p.arguments=["-u",root.appendingPathComponent("mac-app/engine/pipeline.py").path,configURL.path]
            var env=ProcessInfo.processInfo.environment; env["PATH"]="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"; env["PYTHONUNBUFFERED"]="1"; p.environment=env
            p.currentDirectoryURL=root; p.standardOutput=handle; p.standardError=handle
            do { try p.run() }
            catch {
                let failure:[String:Any] = ["stage":"error","message":error.localizedDescription]
                try? JSONSerialization.data(withJSONObject:failure).write(to:dir.appendingPathComponent("status.json"),options:.atomic)
                _ = try? historyCall("record",extra:["--job",dir.path]); try? handle.close(); throw error
            }
            try handle.close()
            process=p; job=dir; output=nil; create.isEnabled=false; cancel.isEnabled=true; result.isEnabled=false; status.stringValue="Запуск…"; log.string=""
            timer=Timer.scheduledTimer(withTimeInterval:1,repeats:true){[weak self] _ in self?.refresh()}
        } catch { alert(error.localizedDescription) }
    }
    func refresh() {
        guard let job=job, let process=process else{return}
        if let text=try? String(contentsOf:job.appendingPathComponent("run.log"),encoding:.utf8){log.string=String(text.suffix(18000));log.scrollToEndOfDocument(nil)}
        var stage=""
        if let data=try? Data(contentsOf:job.appendingPathComponent("status.json")),let s=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any] {
            status.stringValue=s["message"] as? String ?? ""; stage=s["stage"] as? String ?? ""
            if let path=s["output"] as? String, FileManager.default.fileExists(atPath:path) {output=URL(fileURLWithPath:path);result.isEnabled=true}
        }
        if !process.isRunning {
            if stage != "done" && stage != "error" && stage != "upload_error" && stage != "cancelled" {status.stringValue="Процесс остановлен. Файлы и журнал сохранены."}
            self.process=nil; timer?.invalidate();timer=nil;create.isEnabled=true;cancel.isEnabled=false
        }
    }
    @objc func stop(){process?.terminate();status.stringValue="Остановка вычислений…";cancel.isEnabled=false}
    @objc func openResult(){if let output=output {NSWorkspace.shared.activateFileViewerSelecting([output])}}
    func windowShouldClose(_ sender:NSWindow)->Bool { if process != nil {alert("Сначала останови генерацию и дождись завершения процесса.");return false};return true }
    func applicationShouldTerminate(_ sender:NSApplication)->NSApplication.TerminateReply {if process != nil {alert("Сначала останови генерацию. Проект сохранён в папке jobs.");return .terminateCancel};return .terminateNow}
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool{return true}
}
if CommandLine.arguments.count > 1 {
    let project=Bundle.main.object(forInfoDictionaryKey:"AvatarProjectRoot") as? String ?? ""
    let python=project+"/local-avatar/.venv-lipsync/bin/python"
    let arguments=[python,project+"/mac-app/engine/studio_cli.py"]+Array(CommandLine.arguments.dropFirst())
    var pointers=arguments.map {strdup($0)};pointers.append(nil)
    execv(python,&pointers)
    perror("Не удалось запустить CLI студии");exit(127)
}
let app=NSApplication.shared
let delegate=App(); app.delegate=delegate; app.setActivationPolicy(.regular);app.run()
