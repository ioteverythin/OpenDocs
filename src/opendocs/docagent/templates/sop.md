# Standard Operating Procedure — {{project_name}}

## 1. Setup & Prerequisites

### Prerequisites

{{prerequisites}}

### Installation

{{installation}}

### Environment Configuration

1. Copy the example environment file (if available)
2. Set required environment variables
3. Verify database/service connections

## 2. Run Instructions

### Development Mode

{{dev_run}}

### Production Mode

{{prod_run}}

## 3. Deployment

{{deployment}}

### CI/CD Pipeline

{{ci_cd}}

## 4. Monitoring

### Health Checks

- Monitor application logs for errors
- Check resource utilisation (CPU, memory, disk)
- Set up alerts for critical failures

## 5. Troubleshooting

### Common Issues

| Issue | Possible Cause | Resolution |
|-------|---------------|------------|
| Application won't start | Missing dependencies | Re-run install commands |
| Connection refused | Service not running | Check service status |
| Build failure | Incompatible versions | Verify dependency versions |

### Log Locations

- Application logs: `./logs/` or stdout
