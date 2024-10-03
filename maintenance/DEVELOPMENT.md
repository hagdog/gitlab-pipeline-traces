# Background

This page provides basic tips to aid with development of code in this directory.

# Running Scripts

## Python

The scripts operate in different environments. The following example demonstrates how to set up a Python virtual environment for the script to operate in.

##### Python Setup in this Example:

Ensure that Python version >= 3.8 is installed on your system

```
$ cd ~/code/ExportTracesRepo
~/code/ExportTracesRepo$ python3.x -m venv venv-gitlab
~/code/ExportTracesRepo$ source venv-gitlab/bin/activate
(venv-gitlab) ~/code/ExportTracesRepo$ python3 -m pip install -r maintenance/requirements-gitlab-registry
```

## Credentials

Various systems need credentials. Files in this repository for should provide guidance. In this example, credential management is found in the `templates/proj/cred-helpers.yml` file. The commands in that file can be run in your terminal:

```
(venv-gitlab) ~/code/ExportTracesRepo$ export PG_USER="dw_configuration_management_user"
(venv-gitlab) ~/code/ExportTracesRepo$ export RDSHOST='redacted.us-west-2.rds.amazonaws.com'
(venv-gitlab) ~/code/ExportTracesRepo$ export PGPASSWORD="$(aws rds generate-db-auth-token --hostname $RDSHOST --port 5432 --region us-west-2 --username $PG_USER )"
```

## Execute

The script can be simply run on the command line. Be sure and set the DRY*RUN variable unless your intent is to clean the registry rather than developing and observing what \_would* happen:

```
(venv-gitlab) ~/code/ExportTracesRepo$ DRY_RUN=true ./maintenance/clean-gitlabf-registry.py
```

Or, you can run the script in the debugger in VSCode. Starting VSCode in this environment ensures that Python modules and crentials are available in VSCode. Just run the scripts using the VSCode debugger.

```
(venv-gitlab) ~/code/ExportTracesRepo$ vscode .
```
