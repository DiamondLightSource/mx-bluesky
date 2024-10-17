"""
Deploy latest release of mx_bluesky either on a beamline or in dev mode.
"""

import argparse
import os
from subprocess import PIPE, CalledProcessError, Popen

from git import Repo
from packaging.version import Version

recognised_beamlines = ["i04", "i24"]

help_message = """
To deploy mx_bluesky on a specific beamline, pass only the --beamline argument.
This will put the latest release in /dls_sw/ixx/software/bluesky/mx_bluesky_v#.#.# and \
set the permissions accordingly. \n
To run in dev mode instead, only the --dev-path should be passed, a test release will \
be placed in {dev_path}/mxbluesky_release_test/bluesky. \n
Finally, if both a --beamline and a --dev-path are specified, a beamline-specific test \
deployment will be put in the test directory.
"""


class repo:
    # Set name, setup remote origin, get the latest version"""
    def __init__(self, name: str, repo_args):
        self.name = name
        self.repo = Repo(repo_args)

        self.origin = self.repo.remotes.origin
        self.origin.fetch()

        self.versions = [t.name for t in self.repo.tags]
        self.versions.sort(key=Version, reverse=True)
        print(f"Found {self.name}_versions:\n{os.linesep.join(self.versions)}")
        self.latest_version_str = self.versions[0]

    def deploy(self, url, beamline: str | None = None):
        print(f"Cloning latest version {self.name} into {self.deploy_location}")

        deploy_repo = Repo.init(self.deploy_location)
        deploy_origin = deploy_repo.create_remote("origin", self.origin.url)

        deploy_origin.fetch()
        deploy_repo.git.checkout(self.latest_version_str)

        print("Setting permissions")
        groups_to_give_permission = get_permission_groups(beamline)
        setfacl_params = ",".join(
            [f"g:{group}:rwx" for group in groups_to_give_permission]
        )

        # Set permissions and defaults
        os.system(f"setfacl -R -m {setfacl_params} {self.deploy_location}")
        os.system(f"setfacl -dR -m {setfacl_params} {self.deploy_location}")

    # Deploy location depends on the latest mx_bluesky version (...software/bluesky/mx_bluesky_V...)
    def set_deploy_location(self, release_area):
        self.deploy_location = os.path.join(release_area, self.name)
        if os.path.isdir(self.deploy_location):
            raise Exception(
                f"{self.deploy_location} already exists, stopping deployment for {self.name}"
            )


# Get permission groups depending on beamline/dev install
def get_permission_groups(beamline: str | None = None) -> list:
    beamline_groups = ["gda2", "dls_dasc"]
    if beamline:
        beamline_groups.append(f"{beamline}_staff")
    return beamline_groups


# Get the release directory based off the beamline and the latest mx_bluesky version
def get_beamline_and_release_dir_from_args(repo: repo) -> tuple[str | None, str]:
    if repo.name != "mx-bluesky":
        raise ValueError("This function should only be used with the mx-bluesky repo")

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description=__doc__,
        epilog=help_message,
    )
    parser.add_argument(
        "--beamline",
        type=str,
        choices=recognised_beamlines,
        help="The beamline to deploy mx-bluesky to.",
    )
    parser.add_argument(
        "--dev-path",
        type=str,
        help="Path for dev deployment.",
    )

    args = parser.parse_args()
    if not args.beamline:
        print("Running as dev")
        if not args.dev_path:
            raise ValueError("The path for the dev install hasn't been specified.")
        return None, os.path.join(args.dev_path, "mxbluesky_release_test/bluesky")
    elif args.beamline and args.dev_path:
        print(
            f"""
            WARNING! Running a {args.beamline} deployment as dev, which will be placed
            in {args.dev_path}.
            """
        )
        return args.beamline, os.path.join(
            args.dev_path, f"mxbluesky_{args.beamline}_release_test/bluesky"
        )
    else:
        print(f"Deploying on beamline {args.beamline}.")
        return args.beamline, f"/dls_sw/{args.beamline}/software/bluesky"


def run_process_and_print_output(proc_to_run):
    with Popen(proc_to_run, stdout=PIPE, bufsize=1, universal_newlines=True) as p:
        if p.stdout is not None:
            for line in p.stdout:
                print(line, end="")
    if p.returncode != 0:
        raise CalledProcessError(p.returncode, p.args)


if __name__ == "__main__":
    mx_repo = repo(
        name="mx-bluesky",
        repo_args=os.path.join(os.path.dirname(__file__), "../../.git"),
    )

    # Gives path to /bluesky
    beamline, release_area = get_beamline_and_release_dir_from_args(mx_repo)

    release_area_version = os.path.join(
        release_area, f"mx-bluesky_{mx_repo.latest_version_str}"
    )

    print(f"Putting releases into {release_area_version}")

    dodal_repo = repo(
        name="dodal",
        repo_args=os.path.join(os.path.dirname(__file__), "../../../dodal/.git"),
    )

    dodal_repo.set_deploy_location(release_area_version)
    mx_repo.set_deploy_location(release_area_version)

    # Deploy mx_bluesky repo
    mx_repo.deploy(mx_repo.origin.url, beamline)

    # Get version of dodal that latest mx_bluesky version uses
    with open(f"{release_area_version}/mx-bluesky/pyproject.toml") as setup_file:
        dodal_url = [
            line
            for line in setup_file
            if "https://github.com/DiamondLightSource/python-dodal" in line
        ]

    # Now deploy the correct version of dodal
    dodal_repo.deploy(dodal_url, beamline)

    # Set up environment and run /dls_dev_env.sh...
    os.chdir(mx_repo.deploy_location)
    print(f"Setting up environment in {mx_repo.deploy_location}")

    if mx_repo.name == "mx-bluesky":
        run_process_and_print_output("./utility_scripts/dls_dev_env.sh")

    # If on beamline I24 also deploy the screens to run ssx collections
    if beamline == "i24":
        print("Setting up edm screens for serial collections on I24.")
        run_process_and_print_output("./utility_scripts/deploy/deploy_edm_for_ssx.sh")

    move_symlink = input(
        """Move symlink (y/n)? WARNING: this will affect the running version!
Only do so if you have informed the beamline scientist and you're sure mx-bluesky is not running.
"""
    )
    # Creates symlink: software/bluesky/mx_bluesky_version -> software/bluesky/mx_bluesky
    if move_symlink == "y":
        live_location = os.path.join(release_area, "mx-bluesky")
        new_tmp_location = os.path.join(release_area, "tmp_art")
        os.symlink(mx_repo.deploy_location, new_tmp_location)
        os.rename(new_tmp_location, live_location)
        print(f"New version moved to {live_location}")
    else:
        print("Quitting without latest version being updated")
