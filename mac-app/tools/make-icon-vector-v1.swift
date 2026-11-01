// Vector source for the application icon. Generated PNG/ICNS stay in build/.
import AppKit
let destination=URL(fileURLWithPath:CommandLine.arguments[1])
try FileManager.default.createDirectory(at:destination,withIntermediateDirectories:true)
let orange=NSColor(srgbRed:1,green:0.36,blue:0.12,alpha:1)
func icon(_ size:Int)->Data {
    let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:size,pixelsHigh:size,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    let context=NSGraphicsContext(bitmapImageRep:bitmap)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current=context
    context.cgContext.scaleBy(x:CGFloat(size)/1024,y:CGFloat(size)/1024)
    let tile=NSBezierPath(roundedRect:NSRect(x:64,y:64,width:896,height:896),xRadius:200,yRadius:200)
    let gradient=NSGradient(starting:NSColor(srgbRed:0.18,green:0.19,blue:0.22,alpha:1),ending:NSColor(srgbRed:0.055,green:0.06,blue:0.075,alpha:1))!
    gradient.draw(in:tile,angle:270)
    NSColor(white:1,alpha:0.1).setStroke(); tile.lineWidth=3; tile.stroke()
    orange.setStroke()
    let ring=NSBezierPath(ovalIn:NSRect(x:220,y:220,width:584,height:584)); ring.lineWidth=30; ring.stroke()
    orange.setFill()
    NSBezierPath(ovalIn:NSRect(x:419,y:505,width:186,height:200)).fill()
    let shoulders=NSBezierPath(); shoulders.move(to:NSPoint(x:341,y:344)); shoulders.curve(to:NSPoint(x:683,y:344),controlPoint1:NSPoint(x:341,y:531),controlPoint2:NSPoint(x:683,y:531)); shoulders.line(to:NSPoint(x:683,y:330)); shoulders.line(to:NSPoint(x:341,y:330)); shoulders.close(); shoulders.fill()
    NSColor(srgbRed:0.085,green:0.09,blue:0.105,alpha:1).setFill()
    NSBezierPath(ovalIn:NSRect(x:635,y:181,width:229,height:229)).fill()
    orange.setFill(); NSBezierPath(ovalIn:NSRect(x:652,y:198,width:195,height:195)).fill()
    NSColor(srgbRed:0.085,green:0.09,blue:0.105,alpha:1).setFill()
    let play=NSBezierPath(); play.move(to:NSPoint(x:724,y:245)); play.line(to:NSPoint(x:724,y:347)); play.line(to:NSPoint(x:799,y:296)); play.close(); play.fill()
    NSGraphicsContext.restoreGraphicsState()
    return bitmap.representation(using:.png,properties:[:])!
}
for size in [16,32,128,256,512] {
    try icon(size).write(to:destination.appendingPathComponent("icon_\(size)x\(size).png"))
    try icon(size*2).write(to:destination.appendingPathComponent("icon_\(size)x\(size)@2x.png"))
}
