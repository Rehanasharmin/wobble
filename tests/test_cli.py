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

    def test_apk_share_parser(self):
        args = self.parser.parse_args(["apk", "share", "app-debug.apk", "--dest", "/custom/path"])
        self.assertEqual(args.command, "apk")
        self.assertEqual(args.subcommand, "share")
        self.assertEqual(args.file, "app-debug.apk")
        self.assertEqual(args.dest, "/custom/path")

    def test_apk_sign_parser(self):
        args = self.parser.parse_args(["apk", "sign", "app.apk", "--keystore", "key.jks", "--alias", "mykey"])
        self.assertEqual(args.command, "apk")
        self.assertEqual(args.subcommand, "sign")
        self.assertEqual(args.keystore, "key.jks")
        self.assertEqual(args.alias, "mykey")

    def test_project_remove_parser(self):
        args = self.parser.parse_args(["project", "remove", "myoldapp"])
        self.assertEqual(args.command, "project")
        self.assertEqual(args.subcommand, "remove")
        self.assertEqual(args.name, "myoldapp")

    def test_deps_list_parser(self):
        args = self.parser.parse_args(["deps", "list"])
        self.assertEqual(args.command, "deps")
        self.assertEqual(args.subcommand, "list")


if __name__ == "__main__":
    unittest.main()
