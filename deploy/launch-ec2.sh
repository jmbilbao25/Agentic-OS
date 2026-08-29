#!/usr/bin/env bash
# Launch the always-on box. Run this from AWS CloudShell (it has credentials).
#
#   bash launch-ec2.sh
#
# Creates: a security group allowing SSH from your current IP only, a keypair if
# you have none, and one t3.micro with 30 GB gp3. Nothing else is opened to the
# internet — the web UI is published through Tailscale Funnel, not a public port.
set -euo pipefail

NAME="${NAME:-agentos}"
TYPE="${TYPE:-t3.micro}"
DISK="${DISK:-30}"
REGION="${REGION:-$(aws configure get region || echo us-east-1)}"
KEY="${KEY:-agentos-key}"

say() { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }

say "region $REGION · type $TYPE · disk ${DISK}GB"

# ---- AMI: latest Amazon Linux 2023, resolved from SSM so it never goes stale
AMI=$(aws ssm get-parameters \
  --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --region "$REGION" --query 'Parameters[0].Value' --output text)
say "AMI $AMI"

# ---- keypair
if ! aws ec2 describe-key-pairs --key-names "$KEY" --region "$REGION" >/dev/null 2>&1; then
  say "creating keypair $KEY -> ./$KEY.pem  (keep this file, it is the only copy)"
  aws ec2 create-key-pair --key-name "$KEY" --region "$REGION" \
    --query KeyMaterial --output text > "$KEY.pem"
  chmod 400 "$KEY.pem"
else
  say "keypair $KEY already exists (make sure you still have the .pem)"
fi

# ---- security group: SSH from this IP only
MYIP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')
SG=$(aws ec2 describe-security-groups --region "$REGION" \
  --filters "Name=group-name,Values=$NAME-sg" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo None)

if [ "$SG" = "None" ] || [ -z "$SG" ]; then
  say "creating security group $NAME-sg"
  SG=$(aws ec2 create-security-group --group-name "$NAME-sg" --region "$REGION" \
    --description "AgentOS: SSH only; web is published via Tailscale Funnel" \
    --query GroupId --output text)
fi
aws ec2 authorize-security-group-ingress --group-id "$SG" --region "$REGION" \
  --protocol tcp --port 22 --cidr "${MYIP}/32" >/dev/null 2>&1 \
  && say "allowed SSH from ${MYIP}/32" \
  || say "SSH rule for ${MYIP}/32 already present"

# ---- launch
say "launching…"
IID=$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI" --instance-type "$TYPE" --key-name "$KEY" \
  --security-group-ids "$SG" \
  --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":${DISK},\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true,\"Encrypted\":true}}]" \
  --metadata-options 'HttpTokens=required' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' --output text)

aws ec2 wait instance-running --instance-ids "$IID" --region "$REGION"
IP=$(aws ec2 describe-instances --instance-ids "$IID" --region "$REGION" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

cat <<EOF

$(printf '\033[1;32m')instance ready$(printf '\033[0m')
  id   $IID
  ip   $IP
  ssh  ssh -i $KEY.pem ec2-user@$IP

next:
  scp -i $KEY.pem deploy/provision.sh ec2-user@$IP:
  ssh -i $KEY.pem ec2-user@$IP 'bash provision.sh'

cost: ${TYPE} + ${DISK}GB gp3 is roughly \$10/month. Set a billing alarm:
  aws cloudwatch put-metric-alarm --alarm-name agentos-spend \\
    --namespace AWS/Billing --metric-name EstimatedCharges \\
    --statistic Maximum --period 21600 --threshold 20 \\
    --comparison-operator GreaterThanThreshold --evaluation-periods 1 \\
    --region us-east-1

to stop paying for compute (disk still bills):
  aws ec2 stop-instances --instance-ids $IID --region $REGION
to destroy entirely:
  aws ec2 terminate-instances --instance-ids $IID --region $REGION
EOF
