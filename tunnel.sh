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

aws ssm start-session \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSession \
  --parameters portNumber=22,localPortNumber=$LOCAL_SSH_PORT &

# Wait for the tunnel to be ready
until nc -z localhost $LOCAL_SSH_PORT 2>/dev/null; do sleep 1; done

sleep 1

# Use SSH to forward multiple ports at once
ssh obi-staging -N \
  -L 4444:staging.cell-a.openbraininstitute.org:443
