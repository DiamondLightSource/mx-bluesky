"""
Deploy latest release of mx-bluesky either on a beamline or in dev mode.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from typing import NamedTuple
from uuid import uuid1

from create_venv import run_process_and_print_output, setup_venv
from git import Repo
from packaging.version import VERSION_PATTERN, Version

usage = "python %(prog)s beamline [options]"

recognised_beamlines = ["i03", "i04", "i24", "i02-1", "i23"]

VERSION_PATTERN_COMPILED = re.compile(
    f"^{VERSION_PATTERN}$", re.VERBOSE | re.IGNORECASE
)

DEV_DEPLOY_LOCATION = "/scratch/30day_tmp/mx-bluesky_release_test/bluesky"

MAX_DEPLOYMENTS = 4

help_message = f"""
To deploy mx_bluesky on a specific beamline, using the control machine to create the \
environment and without kubernetes, only the beamline argument needs to be passed.
This will put the latest release in /dls_sw/ixx/software/bluesky/mx_bluesky_v#.#.# and \
set the permissions accordingly. \n
To run in dev mode, pass also the --dev option. This will place a test release in \
{DEV_DEPLOY_LOCATION}. \n
"""


class Options(NamedTuple):
    release_dir: str
    kubernetes: bool = False
    print_release_dir: bool = False
    quiet: bool = False
    dev_mode: bool = False
    prune_deployments: bool = True

    # NOTE For i24 for now will need to set it to false from the command line
    use_control_machine: bool = True


class Deployment:
    # Set name, setup remote origin, get the latest version"""
    def __init__(self, name: str, repo_args, options: Options):
        self.name = name
        self.repo = Repo(repo_args)

        self.origin = self.repo.remotes.origin
        self.origin.fetch()
        self.origin.fetch("refs/tags/*:refs/tags/*")

        self.versions = [
            t.name for t in self.repo.tags if VERSION_PATTERN_COMPILED.match(t.name)
        ]
        self.versions.sort(key=Version, reverse=True)

        self.options = options
        if not self.options.quiet:
            print(f"Found {self.name}_versions:\n{os.linesep.join(self.versions)}")

        self.latest_version_str = self.versions[0]

    def deploy(self, beamline: str):
        print(f"Cloning latest version {self.name} into {self.deploy_location}")

        deploy_repo = Repo.init(self.deploy_location)
        deploy_origin = deploy_repo.create_remote("origin", self.origin.url)

        deploy_origin.fetch()
        deploy_origin.fetch("refs/tags/*:refs/tags/*")
        deploy_repo.git.checkout(self.latest_version_str)

        print("Setting permissions")
        groups_to_give_permission = _get_permission_groups(
            beamline, self.options.dev_mode
        )
        setfacl_params = ",".join(
            [f"g:{group}:rwx" for group in groups_to_give_permission]
        )

        # Set permissions and defaults
        os.system(f"setfacl -R -m {setfacl_params} {self.deploy_location}")
        os.system(f"setfacl -dR -m {setfacl_params} {self.deploy_location}")

    # Deploy location depends on the latest hyperion version (...software/bluesky/hyperion_V...)
    def set_deploy_location(self, release_area):
        self.deploy_location = os.path.join(release_area, self.name)
        if os.path.isdir(self.deploy_location):
            raise Exception(
                f"{self.deploy_location} already exists, stopping deployment for {self.name}"
            )


# Get permission groups depending on beamline/dev install
def _get_permission_groups(beamline: str, dev_mode: bool = False) -> list:
    beamline_groups = ["gda2", "dls_dasc"]
    if not dev_mode:
        beamline_groups.append(f"{beamline}_staff")
    return beamline_groups


def _create_environment_from_control_machine(
    mx_repo: Deployment,
    path_to_create_venv: str,
    path_to_dls_dev_env: str,
    beamline: str = "i03",
):
    try:
        user = os.environ["USER"]
    except KeyError:
        user = input(
            """Couldn't find username from the environment. Enter FedID in order \
                to SSH to control machine:"""
        )
    cmd = f"ssh {user}@{beamline}-control python3 {path_to_create_venv} {path_to_dls_dev_env} {mx_repo.deploy_location}"

    process = None
    try:
        # Call python script on i03-control to create the environment
        process = subprocess.Popen(cmd, shell=True, text=True, bufsize=1)
        process.communicate()
        if process.returncode != 0:
            print("Error occurred, exiting")
            sys.exit(1)
    except Exception as e:
        print(f"Exception while trying to install venv on i03-control: {e}")
    finally:
        if process:
            process.kill()


def _prune_old_deployments(release_area: str):
    def get_creation_time(deployment):
        # Warning: getctime gives time since last metadata change, not the creation time.
        return os.path.getctime(os.path.join(release_area, deployment))

    deployments = os.listdir(release_area)
    set_of_deployments = set(deployments)

    # Seperates symlinks and deployments
    symlinks = set()
    for item in deployments:
        if os.path.islink(os.path.join(release_area, item)):
            symlinks.add(item)
            set_of_deployments.remove(item)

    sorted_deployments = sorted(set_of_deployments, key=get_creation_time, reverse=True)

    # Excludes most recent deployments
    if len(sorted_deployments) > MAX_DEPLOYMENTS:
        full_path_old_deployments = {
            os.path.join(release_area, deployment)
            for deployment in sorted_deployments[MAX_DEPLOYMENTS:]
        }

        # Excludes deployments that are symlinked
        for link in symlinks:
            link_path = os.path.dirname(os.readlink(os.path.join(release_area, link)))
            if link_path in full_path_old_deployments:
                full_path_old_deployments.remove(link_path)

        # Deletes old deployments
        for old_deployment in full_path_old_deployments:
            print(f"Deleting old deployment {os.path.basename(old_deployment)}")
            shutil.rmtree(old_deployment)


def main(beamline: str, options: Options):
    release_area = options.release_dir
    this_repo_top = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    if not options.quiet:
        print(f"Repo top is {this_repo_top}")

    mx_repo = Deployment(
        name="mx-bluesky",
        repo_args=os.path.join(this_repo_top, ".git"),
        options=options,
    )

    if mx_repo.name != "mx-bluesky":
        raise ValueError("This function should only be used with the mx-bluesky repo.")

    release_area_version = os.path.join(
        release_area, f"mx-bluesky_{mx_repo.latest_version_str}"
    )

    if options.print_release_dir:
        print(release_area_version)
        return

    print(f"Putting releases into {release_area_version}")

    dodal_repo = Deployment(
        name="dodal",
        repo_args=os.path.join(this_repo_top, "../dodal/.git"),
        options=options,
    )

    dodal_repo.set_deploy_location(release_area_version)
    mx_repo.set_deploy_location(release_area_version)

    # Deploy mx_bluesky repo
    mx_repo.deploy(beamline)

    # Now deploy the correct version of dodal
    dodal_repo.deploy(beamline)

    if not options.kubernetes:
        if mx_repo.name == "mx-bluesky":
            path_to_dls_dev_env = os.path.join(
                mx_repo.deploy_location,
                "utility_scripts/dls_dev_env.sh",
            )
            path_to_create_venv = os.path.join(
                mx_repo.deploy_location,
                "utility_scripts/deploy/create_venv.py",
            )

            # SSH into control machine if not in dev mode
            if options.use_control_machine and release_area != DEV_DEPLOY_LOCATION:
                _create_environment_from_control_machine(
                    mx_repo, path_to_create_venv, path_to_dls_dev_env, beamline
                )
            else:
                setup_venv(path_to_dls_dev_env, mx_repo.deploy_location)

    # If on beamline I24 also deploy the screens to run ssx collections
    if beamline == "i24":
        print("Setting up edm screens for serial collections on I24.")
        run_process_and_print_output("./utility_scripts/deploy/deploy_edm_for_ssx.sh")

    def create_symlink_by_tmp_and_rename(dirname, target, linkname):
        tmp_name = str(uuid1())
        target_path = os.path.join(dirname, target)
        linkname_path = os.path.join(dirname, linkname)
        tmp_path = os.path.join(dirname, tmp_name)
        os.symlink(target_path, tmp_path)
        os.rename(tmp_path, linkname_path)

    move_symlink = input(
        """Move symlink (y/n)? WARNING: this will affect the running version! \
            Only do so if you have informed the beamline scientist and you're sure \
            mx-bluesky is not running."""
    )
    if move_symlink == "y":
        # NOTE at some point need a better distinction between beamlines that use
        # hyperions and the rest of them. For now it's just i24 asaik.
        if beamline == "i24":
            live_location = os.path.join(release_area, "mx-bluesky")
            create_symlink_by_tmp_and_rename(release_area, live_location, "mx-bluesky")
        else:
            old_live_location = os.path.relpath(
                os.path.realpath(os.path.join(release_area, "hyperion")), release_area
            )
            make_live_stable_symlink = input(
                f"""The last live deployment was {old_live_location}, \
                    do you want to set this as the stable version? (y/n)"""
            )
            if make_live_stable_symlink == "y":
                create_symlink_by_tmp_and_rename(
                    release_area, old_live_location, "hyperion_stable"
                )

            relative_deploy_loc = os.path.join(
                os.path.relpath(mx_repo.deploy_location, release_area)
            )
            create_symlink_by_tmp_and_rename(
                release_area, relative_deploy_loc, "hyperion_latest"
            )
            create_symlink_by_tmp_and_rename(
                release_area, "hyperion_latest", "hyperion"
            )
        print(f"New version moved to {mx_repo.deploy_location}")
        print(
            """If running hyperion, to start this version run hyperion_restart \
                from the beamline's GDA"""
        )
    else:
        print("Quitting without latest version being updated")

    if options.prune_deployments:
        _prune_old_deployments(release_area)


# Get the release directory based off the beamline and the latest mx-bluesky version
def _parse_options() -> tuple[str, Options]:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description=__doc__,
        usage=usage,
        epilog=help_message,
    )
    parser.add_argument(
        "beamline",
        type=str,
        choices=recognised_beamlines,
        help="The beamline to deploy mx_bluesky to.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help=f"Test deployment in dev mode, install to {DEV_DEPLOY_LOCATION}.",
    )
    parser.add_argument(
        "--kubernetes",
        action="store_true",
        help="Prepare git workspaces for deployment to kubernetes; do not install virtual environment.",
    )
    parser.add_argument(
        "--print-release-dir",
        action="store_true",
        help="Print the path to the release folder and then exit.",
    )
    parser.add_argument(
        "-nc",
        "--no-control",
        action="store_false",
        help="Do not create environment running from the control machine.",
    )
    parser.add_argument(
        "-pd",
        "--prune-deployments",
        required=False,
        default=True,
        help="Delete deployments which are older than the latest four if they aren't being used in any symlinks",
    )

    args = parser.parse_args()
    if args.dev:
        print("Running as dev")
        release_dir = DEV_DEPLOY_LOCATION
    else:
        release_dir = f"/dls_sw/{args.beamline}/software/bluesky"

    return args.beamline, Options(
        release_dir=release_dir,
        kubernetes=args.kubernetes,
        print_release_dir=args.print_release_dir,
        quiet=args.print_release_dir,
        dev_mode=args.dev,
        prune_deployments=args.prune_deployments,
        use_control_machine=args.no_control,
    )


if __name__ == "__main__":
    beamline, options = _parse_options()
    main(beamline, options)
