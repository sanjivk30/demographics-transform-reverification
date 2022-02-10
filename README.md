# demographics-transform-reverification

## AWS Pipeline
- Pipeline in `.github/workflows/pipeline.yml`
- Deploys Lambda functions to AWS

## Terraform infrastructure
- Pipeline in `.github/workflows/infrastructure.yml`
- Terraform configurations in ´./terraform´

## Sonarqube
- Project page: https://sonarqube.netcompany.com/dashboard?id=NHSDPDS-NHSDPDS (login with NCDMZ)
- Pipeline in `.github/workflows/sonarqube.yml`

## Unit tests
- Pytest is used
- Pipeline in `.github/workflows/unittests.yml`
