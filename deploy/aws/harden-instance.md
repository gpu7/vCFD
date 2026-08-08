# EC2 security hardening — vcfd-mcp

## Applied at AWS API level

| Control | Setting |
|---------|---------|
| Security group SSH | Admin IP `/32` only (updated when harden script runs) |
| Security group 80/443 | `0.0.0.0/0` (public MCP; required for EIP/HTTP and Caddy) |
| IMDSv2 | **Required** |
| IMDS hop limit | **1** (containers cannot reach instance metadata) |
| API termination protection | **On** |
| IAM instance profile | `vcfd-ec2-ssm-profile` → `AmazonSSMManagedInstanceCore` |
| Tags | `Name=vcfd-mcp`, `SecurityHardened=true` |
| Root volume encryption | Live volume **unencrypted** (AMI-era); encrypted **snapshot copy** created for recovery |
| Elastic IP | Associated (stable admin/MCP IP) |

## OS script (run after Start)

```bash
ssh -i ~/.ssh/vcfd-ec2.pem ubuntu@35.168.122.123
cd /opt/vcfd && sudo git pull origin master   # or reset --hard
sudo bash /opt/vcfd/deploy/aws/harden-os.sh
cd /opt/vcfd
sudo docker compose -f deploy/aws/docker-compose.prod.yml up -d
```

`harden-os.sh` configures:

- Passwordless SSH only, no root login
- UFW + fail2ban
- Unattended security upgrades
- Sysctl anti-spoof / redirect hardening
- Tight modes on `/etc/vcfd/vcfd.env`
- Docker daemon log limits + no userland-proxy

## Optional next steps (not auto-applied)

1. **Restrict 80/443** to your IP if you only use Cloudflare Tunnel (outbound) for Voice.
2. **Encrypted root volume** migration: launch new instance from encrypted snapshot/AMI, reattach EIP.
3. **SSM Session Manager** instead of SSH: after SSM agent is online, remove port 22 from SG.
4. **AWS Config / GuardDuty** at account level.
5. **Rotate** `VCFD_AUTH_TOKEN` after any public paste.

## Verify

```bash
aws ec2 describe-instances --instance-ids i-0b37e51bf775cf954 \
  --query 'Reservations[0].Instances[0].{State:State.Name,IMDS:MetadataOptions,Term:DisableApiTermination,IAM:IamInstanceProfile}'
aws ec2 describe-security-groups --group-ids sg-052d8e33c3c5145a9 \
  --query 'SecurityGroups[0].IpPermissions'
```
