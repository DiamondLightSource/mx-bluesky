# Get Started with mx-bluesky

## Development Environment

We recommend using devcontainers with vscode as the IDE when developing using a DLS machine. Here's how you can set this up:

- Clone this repo using SSH: `git clone git@github.com:DiamondLightSource/mx-bluesky.git`.
- At the same directory level as you were in for step 1, clone dodal using SSH: `git clone git@github.com:DiamondLightSource/dodal.git`.
You should now have a directory structure looking like`/some_path/mx-bluesky` and `/some_path/dodal`.
- In a terminal, move to the mx-bluesky directory and open vscode:

```
cd /some_path/mx-bluesky  
module load vscode  
code .
```

- Make sure you have the [devcontainers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) installed in vscode.
- In vscode, press `shift+ctrl+p`, and type "Dev Containers: Open Folder in Container", then select the mx-bluesky folder.
- Once this has built, in vscode at the top right, click `File -> Open workspace from file`, then select `mx-bluesky/.vscode/mx-bluesky.code-workspace`.
- This should get dodal and mx-bluesky opened up in your workspace with all the correct settings. To prove to yourself that the environment is correct, type `tox -e tests` in a terminal in your devcontainer while inside the dodal and inside the mx-bluesky directory.

### Notes
- The devcontainer initially takes quite a long time to build. It will be much faster every other time, and only needs to be rebuild if we change the container environment.
- The first time you make a commit after building, you will need to follow some git prompts to set your git name and email.


## Supported Python versions


As a standard for the python versions to support, we are using the [numpy deprecation policy] (https://numpy.org/neps/nep-0029-deprecation_policy.html)

Currently supported versions are: 3.11, 3.12.
