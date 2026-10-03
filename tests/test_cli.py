"""
Test CLI parser, arguments, options, and commands.
"""

import unittest
from wobble.cli import build_parser, main
from wobble import __version__


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_version_string(self):
        self.assertIsNotNone(__version__)

    def test_parser_commands(self):
        command_inputs = {
            "create": ["create", "android", "dummyapp"],
            "project": ["project"],
            "android": ["android"],
            "web": ["web"],
            "apk": ["apk"],
            "deps": ["deps"],
            "doctor": ["doctor"],
            "plugin": ["plugin"],
            "config": ["config"],
            "clean": ["clean"],
            "update": ["update"],
            "schema": ["schema"],
            "build": ["build"],
            "dev": ["dev"],
            "preview": ["preview"]
        }
        for cmd, argv in command_inputs.items():
            args = self.parser.parse_args(argv)
            self.assertEqual(args.command, cmd)

    def test_create_parser_options(self):
        args = self.parser.parse_args(["create", "android", "testapp", "--package", "com.test.app"])
        self.assertEqual(args.command, "create")
        self.assertEqual(args.type, "android")
        self.assertEqual(args.name, "testapp")
        self.assertEqual(args.package, "com.test.app")

    def test_json_flag(self):
        args = self.parser.parse_args(["--json", "doctor"])
        self.assertTrue(args.json)
        self.assertEqual(args.command, "doctor")

    def test_web_dev_parser(self):
        args = self.parser.parse_args(["web", "dev", "--port", "8080", "--host", "127.0.0.1"])
        self.assertEqual(args.command, "web")
        self.assertEqual(args.subcommand, "dev")
        self.assertEqual(args.port, 8080)
        self.assertEqual(args.host, "127.0.0.1")

    def test_apk_info_parser(self):
        args = self.parser.parse_args(["apk", "info", "app-debug.apk"])
        self.assertEqual(args.command, "apk")
        self.assertEqual(args.subcommand, "info")
        self.assertEqual(args.file, "app-debug.apk")


if __name__ == "__main__":
    unittest.main()
