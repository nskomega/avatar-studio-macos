from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
from pronunciation import Lexicon, for_tts, targeted_tts


class PronunciationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / 'test.sqlite3'
        with sqlite3.connect(self.database) as connection:
            connection.execute('CREATE TABLE words (word TEXT PRIMARY KEY, variants TEXT)')
            connection.executemany('INSERT INTO words VALUES (?, ?)', [
                ('пароля', json.dumps(['пар+оля'])),
                ('замок', json.dumps(['з+амок', 'зам+ок'])),
            ])
        self.lexicon = Lexicon(self.database, overrides={'способы': 'спо́собы'})

    def tearDown(self):
        self.lexicon.close()
        self.directory.cleanup()

    def test_lookup_and_case_preserve_punctuation_and_latin(self):
        result = self.lexicon.annotate('Способы, ПАРОЛЯ: passkeys / SMS!')
        self.assertEqual(result['marked'], 'Спо́собы, ПАРО́ЛЯ: passkeys / SMS!')
        self.assertEqual(result['issues'], [])

    def test_ambiguous_and_unknown_are_not_guessed(self):
        result = self.lexicon.annotate('замок неизвестное')
        self.assertEqual(result['marked'], 'замок неизвестное')
        self.assertEqual([issue['status'] for issue in result['issues']], ['ambiguous', 'unknown'])
        self.assertEqual(result['issues'][0]['candidates'], ['за́мок', 'замо́к'])

    def test_existing_stress_is_idempotent(self):
        text = 'Спо́собы, паро́ля.'
        self.assertEqual(self.lexicon.annotate(text)['marked'], text)

    def test_capital_stress_mode(self):
        self.assertEqual(for_tts('Откро́й спо́собы', 'capital'), 'ОткрОй спОсобы')

    def test_targeted_mode_does_not_change_surrounding_words(self):
        self.assertEqual(targeted_tts('Открой настройки безопасности: способы входа.'),
                         'ОткрОй настройки безопасности: спОсобы входа.')

    def test_reported_words_have_requested_stress(self):
        lexicon = Lexicon(Path(self.directory.name) / 'absent.sqlite3')
        expected = {'двухфакторка': 'двухфа́кторка', 'пароля': 'паро́ля',
                    'фишингу': 'фи́шингу', 'открой': 'откро́й', 'способы': 'спо́собы',
                    'добавь': 'доба́вь', 'пригодится': 'пригоди́тся'}
        for word, stressed in expected.items():
            self.assertEqual(lexicon.lookup(word)[0], [stressed])
        lexicon.close()

    def test_missing_dictionary_is_explicit(self):
        lexicon = Lexicon(Path(self.directory.name) / 'absent.sqlite3', overrides={})
        self.assertFalse(lexicon.annotate('пароля')['dictionary_available'])
        self.assertEqual(lexicon.annotate('пароля')['issues'][0]['status'], 'dictionary_missing')
        lexicon.close()


if __name__ == '__main__':
    unittest.main()
