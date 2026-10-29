import unittest
from unittest.mock import patch
from companion import fetch_wallpaper
from adb_tools import AdbError

class CompanionTests(unittest.TestCase):
    def test_failure_never_pulls_old_image(self):
        class Fake:
            def __init__(self): self.calls = []
            def shell(self, command):
                self.calls.append(command)
                if command.startswith("am broadcast"): return "Broadcast completed: result=0"
                if command.startswith("cat "): return "ERROR: permission"
                return ""
            def _exec(self, *args, **kwargs): raise AssertionError("must not pull")
        fake = Fake()
        with self.assertRaises(AdbError): fetch_wallpaper(fake)
        self.assertTrue(fake.calls[0].startswith("rm -f "))

if __name__ == "__main__": unittest.main()
