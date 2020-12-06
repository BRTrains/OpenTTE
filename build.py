import json
import os
import sys

from argparse import ArgumentParser
from pathlib import Path
from shutil import copy
from subprocess import Popen


def check_project_structure(src_directory: Path, lang_directory: Path):
    # Check that the project is properly structured
    if not src_directory.exists():
        print("%s directory not found." % src_directory)
        return False
    if not lang_directory.exists():
        print("%s directory not found. Assuming hard-coded strings (this is not best practice)" % lang_directory)

    # Find the grf, railtypes, and templates files
    if not src_directory.joinpath("grf.pnml").exists():
        print("%s/grf.pnml not found. It should contain the grf block" % src_directory)
        return False
    if not src_directory.joinpath("railtypes.pnml").exists():
        print("%s/railtypes.pnml not found. It should contain the railtypetable block" % src_directory)
        return False
    if not src_directory.joinpath("templates.pnml").exists():
        print("%s/templates.pnml not found. Assuming no templates are required" % src_directory)

    print("Project structure is correct\n")
    return True


class PnmlCompiler:

    def __init__(self, src_directory: Path, build_directory: Path):
        self.src_directory = src_directory
        self.build_directory = build_directory
        self.SPECIAL_FILES = [
            self.src_directory.joinpath("grf.pnml"),
            self.src_directory.joinpath("railtypes.pnml"),
            self.src_directory.joinpath("templates.pnml"),
        ]

    @staticmethod
    def _copy_file(source_file: Path, destination_file: Path):
        # If the source_file doesn't exist, exit
        if not source_file.exists():
            print("The file %s does not exist" % source_file)
            return

        # Read the source file and append it to destination file
        print("Reading file %s" % source_file)
        with destination_file.open("a") as dst_file:
            with source_file.open("r") as src_file:
                dst_file.write("// %s\n\n" % source_file)
                dst_file.write(src_file.read())
            dst_file.write("\n\n")

    def _find_pnml_files(self):
        file_dict = {}
        # Iterate through all files in src_directory recursively, finding any that end in .pnml
        for path in self.src_directory.rglob("*.pnml"):
            # Don't add the special ones
            if path not in self.SPECIAL_FILES:
                file_dict.setdefault(path.parent.name, [])
                file_dict[path.parent.name].append(path)
        return file_dict

    def compile(self, nml_file: Path):
        print("Compiling nml file %s" % nml_file)
        if nml_file.exists():
            nml_file.unlink()  # In Python 3.6 first param is missing

        # Compile the special files first
        for special_file in self.SPECIAL_FILES:
            self._copy_file(special_file, nml_file)

        # Get a list of all the pnml files in src
        file_list = self._find_pnml_files()
        pnml_files = []
        # Read all the files in folders that begin with "_" into the final nml
        for directory in file_list:
            if directory.startswith("_"):
                for file in file_list[directory]:
                    file = Path(file)
                    self._copy_file(file, nml_file)
            else:
                pnml_files += file_list[directory]

        # Read the regular files
        for file in sorted(pnml_files):
            file = Path(file)
            self._copy_file(file, nml_file)

        print("Compiled all *.pnml files into %s\n" % nml_file)


class GrfCompiler:

    @staticmethod
    def compile(nml_file: Path, grf_file: Path, lang_directory: Path):
        try:
            # Check if we have the nml package
            import nml.main
            # setup parameters for nml
            parameters = [str(nml_file), "--grf", str(grf_file)]
            if lang_directory.exists():
                # If we have a lang directory, add it to the parameters
                parameters += ["--lang", str(lang_directory)]
            # Try to compile the nml file
            print("nml parameters: %s" % parameters)
            nml.main.main(parameters)
        except ImportError:
            # nml isn't installed
            print("nml is not installed. You can get it using 'pip install nml'")
            return False
        except SystemExit:
            # nml uses sys.exit(), so catch this to stop the program exiting
            print("Finished compiling grf file: %s\n" % grf_file)
        return True


class Game:

    @staticmethod
    def _detect_platform_settings(platform_settings_file: Path):
        print("Detecting platform settings")
        platform_settings = {}

        if platform_settings_file.exists():
            print("Found existing platform settings file %s" % platform_settings_file)
            with platform_settings_file.open("r") as file:
                try:
                    platform_settings = json.loads(file.read())
                except json.decoder.JSONDecodeError:
                    print("Settings in file was invalid json. Ignoring.")

        elif sys.platform.startswith("linux"):
            platform_settings = {
                "newgrf_directory": Path.home().joinpath(".openttd", "newgrf"),
                "executable_path": "/usr/bin/openttd",
                "executable_params": ["-t", "1920", "-g"],
                "kill_cmd": ["killall", "openttd"],
            }

        elif sys.platform.startswith("win32"):
            platform_settings = {
                "newgrf_directory": str(Path.home().joinpath("Documents", "OpenTTD", "newgrf")),
                "executable_path": "C:/Program Files/OpenTTD/openttd.exe",
                "executable_params": ["-t", "1920", "-g"],
                "kill_cmd": ["taskkill.exe", "/IM", "openttd.exe"],
            }

        platform_settings["platform"] = sys.platform
        print("Detected platform settings: %s" % platform_settings)

        for setting in ("newgrf_directory", "executable_path"):
            path = Path(platform_settings.get(setting, "/dev/non-existent-path"))
            while not path.exists():
                platform_settings[setting] = input("Setting %s: %s is not valid, enter valid path: " % (setting, path))
                path = Path(platform_settings.get(setting))

        for setting in ["executable_params", "kill_cmd"]:
            while not platform_settings.get(setting):
                platform_settings[setting] = input("Enter %s: " % setting).split(" ")

        print("File %s - Saving platform settings: %s" % (platform_settings_file, platform_settings))
        with platform_settings_file.open("w") as file:
            file.write(json.dumps(platform_settings, indent=4))

        return platform_settings

    @staticmethod
    def _kill(platform_settings: dict):
        print("Killing existing processes using kill_cmd: %s" % platform_settings["kill_cmd"])
        try:
            kill_process = Popen(platform_settings["kill_cmd"])
            kill_process.wait()
        except Exception as e:
            print("Something went wrong when trying to kill processes: %s" % e)

    @staticmethod
    def _copy_grf(grf_file: Path, platform_settings: dict):
        print("Copying %s to %s" % (grf_file, platform_settings["newgrf_directory"]))
        copy(grf_file, Path(platform_settings["newgrf_directory"]))

    @staticmethod
    def _run(platform_settings: dict):
        # Run the game in it's root directory
        print("Running game: %s" % platform_settings["executable_path"])
        # Redirect stdout and stderr
        with open(os.devnull, "w") as null:
            subprocess = Popen(
                [platform_settings["executable_path"], *platform_settings["executable_params"]],
                cwd=Path(platform_settings["executable_path"]).parent,
                stdout=null,
                stderr=null,
            )
            subprocess.wait()
        return 0

    @classmethod
    def run(cls, grf_file: Path):
        platform_settings = cls._detect_platform_settings(grf_file.parent.joinpath("platform_settings.json"))
        cls._kill(platform_settings)
        cls._copy_grf(grf_file, platform_settings)
        return cls._run(platform_settings)


# Main section


def parse_args():
    # Parse arguments
    parser = ArgumentParser(description="Compile pnml files into one nml/grf file")
    parser.add_argument("name")
    parser.add_argument("--src", default="src", help="Source files directory")
    parser.add_argument("--lang", default="lang", help="Language files directory")
    parser.add_argument("--builddir", default="build", help="Build files directory")
    parser.add_argument("--compile", action="store_true", help="Compile the nml file with nml lib")
    parser.add_argument("--run", action="store_true", help="Run the game after compilation")
    return parser.parse_args()


def main():
    args = parse_args()
    src_directory = Path(args.src)
    lang_directory = Path(args.lang)
    build_directory = Path(args.builddir)

    # Check if the project is set up properly
    if not check_project_structure(src_directory, lang_directory):
        return 1

    # Build directory and compiled files
    if not build_directory.exists():
        build_directory.mkdir(parents=True)
    nml_file = build_directory.joinpath("%s.nml" % args.name)
    grf_file = build_directory.joinpath("%s.grf" % args.name)

    # Compile all pnml files into one nml
    pnm_compiler = PnmlCompiler(src_directory, build_directory)
    pnm_compiler.compile(nml_file)

    # If we're compiling grf or running the game
    if args.compile or args.run:
        # Try to compile the GRF
        if not GrfCompiler.compile(nml_file, grf_file, lang_directory):
            return 1
        # Optionally run the game
        if args.run:
            return Game.run(grf_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
