"""Tests for ADB wireless pairing and connection without a physical device."""
import unittest
from unittest.mock import patch

from adb_tools import AdbClient, AdbError, validate_wireless_address


class WirelessTests(unittest.TestCase):
    def test_address_validation(self):
        for address in ("192.168.1.2:37123", "phone.local:5555", "[::1]:4321"):
            self.assertEqual(validate_wireless_address(address), address)
        for address in ("host", "host:0", "host:65536", "::1:123", "host:123 extra"):
            with self.subTest(address=address), self.assertRaises(AdbError):
                validate_wireless_address(address)

    def test_pair_and_connect_are_global_and_report_failures(self):
        client = AdbClient()
        client.serial = "existing-device"
        with patch.object(client, "_exec", return_value="Successfully paired to 192.168.1.2:123") as execute:
            client.pair("192.168.1.2:123", "123456")
            execute.assert_called_once_with("pair", "192.168.1.2:123", "123456", timeout=30, use_serial=False)
        with patch.object(client, "_exec", return_value="failed to connect to device"):
            with self.assertRaises(AdbError):
                client.connect("192.168.1.2:456")
        with patch.object(client, "_exec", return_value="already connected to 192.168.1.2:456"):
            self.assertIn("already connected", client.connect("192.168.1.2:456"))
        with self.assertRaises(AdbError):
            client.pair("192.168.1.2:123", "12ab56")


if __name__ == "__main__":
    unittest.main()
