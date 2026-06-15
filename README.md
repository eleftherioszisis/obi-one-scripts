
# How to launch a task  
  
### 1. Prepare the environment   
  
Install dependencies with `brew`:  
```
brew install uv open-mpi boost cmake
```
  
Check which Python 3.12 is present in the system and pin it for obi-one:  
```
$ python3.12 --version
Python 3.12.13
$ uv python pin 3.12.13
Pinned `.python-version` to `3.12.13`
```
  
Install `obi-one` with the service optional dependencies:  
```
make install-service
```
 
Note 1: installation may fail to unupdated `brain-indexer`, this can be fixed by running `make upgrade-deps` before `make install`.
Note 2: `make install` alone doesn't install python-multipart, which is needed to run the service.
  
  
  
### 2. Establish a tunnel to the launch-system API  
  
Requirements:  
  
- The user needs to have access to AWS staging/prod configured:  
  
In ~/.aws/config:  
```
[profile BastionUserAccess-staging]
sso_session = obi
sso_account_id = 992382665735
sso_role_name = BastionUserAccess
region = us-east-1
output = json

[profile BastionUserAccess-prod]
sso_session = obi
sso_account_id = 671250183987
sso_role_name = BastionUserAccess
region = us-east-1
output = json

[sso-session obi]
sso_start_url = https://openbraininstitute.awsapps.com/start/
sso_region = us-east-1
sso_registration_scopes = sso:account:access
```
  
- Also, Session Manager Plugin needs to be installed:  
    - Installation instructions: [https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)  
    - Troubleshooting: [https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-troubleshooting.html](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-troubleshooting.html)  
  
Create the tunnel (run the script):  
  
[https://github.com/eleftherioszisis/obi-one-scripts/blob/main/tunnel.sh](https://github.com/eleftherioszisis/obi-one-scripts/blob/main/tunnel.sh)  
  
```
#!/bin/bash
set -eux

# Set the profile for the environment
export AWS_PROFILE="BastionUserAccess-staging"

LOCAL_SSH_PORT=2222

aws sso login

# Get the bastion instance ID
INSTANCE_ID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=*Bastion*" "Name=instance-state-name,Values=running" --query 'Reservations[0].Instances[0].InstanceId' --output text)

# Get your username from your AWS identity
BASTION_USERNAME=$(aws sts get-caller-identity --query 'UserId' --output text | cut -d: -f2 | cut -d'@' -f1)

# Start the SSM session
echo "Connecting to instance $INSTANCE_ID as user $BASTION_USERNAME..."

#aws ssm start-session \
#  --target "$INSTANCE_ID" \
#  --document-name AWS-StartPortForwardingSession \
#  --parameters portNumber=22,localPortNumber=$LOCAL_SSH_PORT &

aws ssm start-session \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["staging.cell-a.openbraininstitute.org"],"portNumber":["443"],"localPortNumber":["4444"]}'

# Wait for the tunnel to be ready
until nc -z localhost $LOCAL_SSH_PORT 2>/dev/null; do sleep 1; done

sleep 1

# Use SSH to forward multiple ports at once
#ssh obi-staging -N \
#  -L 4444:staging.cell-a.openbraininstitute.org:443
```
  
Check the tunnel is working properly, run (from another terminal):  
```
$ curl -k "https://127.0.0.1:4444/api/launch-system/version"
```
```
{"app_name":"launch-system","app_version":"2026.4.0","commit_sha":"af7f384653b72930899687e7ef9dd266286477d4"}
```
  
  
  
### 3. Run the service  
  
```
make run-local
```

Note: this is a running service, let it run and switch to another terminal  

To test the server is running:  
```
$ curl http://127.0.0.1:8100/docs

    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
    <title>obi-one - Swagger UI</title>
    </head>
    <body>
    <div id="swagger-ui">
    </div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <!-- `SwaggerUIBundle` is now available on the page -->
    <script>
    const ui = SwaggerUIBundle({
        url: '/openapi.json',
    "dom_id": "#swagger-ui",
"layout": "BaseLayout",
"deepLinking": true,
"showExtensions": true,
"showCommonExtensions": true,
oauth2RedirectUrl: window.location.origin + '/docs/oauth2-redirect',
    presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
    })
    </script>
    </body>
    </html>
```
  
  
  
### 4. Prepare the task launch environment  
  
Since we're testing a change in a remote branch, we need to tell the launch system where to look for the code:  
  
Git diff on `obi-one`:  
```
--- a/launch_scripts/launch_task_for_single_config_asset/dependencies/default.txt
+++ b/launch_scripts/launch_task_for_single_config_asset/dependencies/default.txt
@@ -1 +1 @@
-obi-one
+obi-one @ git+https://github.com/openbraininstitute/obi-one@jplanas/split_deps
```
  
This change needs to be committed and pushed, then we will use that commit ID below.  
From now on, the following changes don't need to be committed.  
  
```
--- a/app/mappings.py
+++ b/app/mappings.py
@@ -15,7 +15,7 @@ from app.schemas.task import (
 )
 from app.types import BuiltinScript, TaskType
 
-APP_TAG = f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}"
+APP_TAG = "commit:9140570d2ac63a6bab3231d786b97bda8e46c6f4"
 OBI_ONE_CODE_PATH = str(Path(settings.OBI_ONE_LAUNCH_PATH) / "main.py")
 OBI_ONE_DEPS_DIR = Path(settings.OBI_ONE_LAUNCH_PATH) / "dependencies"
```
  
  
Next, get the task launch script: [https://github.com/eleftherioszisis/obi-one-scripts/blob/main/run_circuit_extraction_cloud.py](https://github.com/eleftherioszisis/obi-one-scripts/blob/main/run_circuit_extraction_cloud.py)  
  
We need to make a few modifications here:  
- First, identify a `vlab id` and a `proj id` where the user has access to and create a dictionary inside the script:  
  
```
    domains = {
        "cell_a": {
            "virtual_lab_id": "26e4df2d-6a77-42bc-8353-4856e4a1320a",
            "project_id": "94d66b4c-6d71-46e3-a1de-082277cecec8",
        }
    }
```
  
- Use this dictionary to pass it to `RemoteTaskManager`, as well as switching subdomain to `cell_a` and switching to `local` deployment :  
  
```
    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.circuit_extraction,
        subdomain="cell_a",                     # Change to cell_a
        obi_one_deployment="local",             # Change to local
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=domains,                        # Add domains
    )
```
  
- Next, we get a `TOKEN` from OBI staging and set it in the terminal environment:  
  
```
export ACCESS_TOKEN="COPY_YOUR_LONG_TOKEN_HERE”
```
  
  
  
### 5. Launch the task  
  
In this case, we use the script above, so everything is already set. We just need to make sure we're using the uv `venv` created when we first called `make install-service` in the first step. For example:  
  
```
source obi-one/.venv/bin/activate
python run_circuit_extraction_cloud.py
```
  
  
  
For the general case, launch-system tasks are defined in `obi-one/app/mappings.py`: [https://github.com/openbraininstitute/obi-one/blob/main/app/mappings.py](https://github.com/openbraininstitute/obi-one/blob/main/app/mappings.py)  
  
We take one, for example:  
  
```
    TaskType.em_synapse_mapping: TaskDefinition(
        task_type=TaskType.em_synapse_mapping,
        config_type=TaskConfigType.em_synapse_mapping__config,
        activity_type=TaskActivityType.em_synapse_mapping__execution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=2,
            timelimit="00:10",
            compute_cell="local",
        ),
    ),
```
  
- `PythonRepositoryCode` —> specify where to fetch the user code to run from  
	Example:  
  
```
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref="commit:$COMMIT",  # where $COMMIT is the commit we want to test
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
        ),
```
