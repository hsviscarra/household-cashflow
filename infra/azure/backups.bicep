// Backups (F17, ADR-016): a nightly BACPAC export of the database to the private `backups`
// container, a monthly restore drill, and 30-day retention. Added next to main.bicep's resources
// by infra/azure/setup-backups.sh; it doesn't touch the app.
//
// - One user-assigned identity runs both jobs: it is the SQL server's Microsoft Entra admin (the
//   export signs in with it, no password) and may write to the `backups` container only.
// - The export job runs every night at 03:17 Quito time (08:17 UTC).
// - The drill job runs on the 2nd of each month at 04:17 Quito time: it restores the latest
//   backup into a SQL Server that runs beside it in the same job (gone when the job ends) and
//   checks it against the backup's manifest.
// - A lifecycle rule deletes backups after 30 days; drill results are kept a year.

@description('Azure region; the resource group\'s by default.')
param location string = resourceGroup().location

@description('The prefix main.bicep used.')
param prefix string = 'cashflow'

@description('The backup image (infra/ops/Dockerfile), pushed by deploy.yml.')
param image string

@description('GitHub user that owns the GHCR image.')
param ghcrUsername string

@secure()
@description('GitHub classic token with read:packages (the one the app pulls with).')
param ghcrToken string

@secure()
@description('Password of the drill\'s throwaway SQL Server; it only lives during the job.')
param drillSaPassword string = '${newGuid()}Aa1!'

@description('Nightly export, UTC (03:17 in Quito).')
param exportCron string = '17 8 * * *'

@description('Monthly restore drill, UTC (the 2nd at 04:17 in Quito).')
param drillCron string = '17 9 2 * *'

var suffix = uniqueString(resourceGroup().id)

resource sql 'Microsoft.Sql/servers@2023-08-01-preview' existing = {
  name: '${prefix}-sql-${suffix}'
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: take('${prefix}st${suffix}', 24)
}

resource blob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}

resource backups 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = {
  parent: blob
  name: 'backups'
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: '${prefix}-env'
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-backup-id'
  location: location
}

// The export signs in to Azure SQL as this identity. SQL logins (the app's) keep working.
resource entraAdmin 'Microsoft.Sql/servers/administrators@2023-08-01-preview' = {
  parent: sql
  name: 'ActiveDirectory'
  properties: {
    administratorType: 'ActiveDirectory'
    login: identity.name
    sid: identity.properties.clientId
    tenantId: subscription().tenantId
  }
}

// Storage Blob Data Contributor on the backups container only.
resource backupWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(backups.id, identity.id, 'blob-contributor')
  scope: backups
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource retention 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'backups-30-days'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: [ 'blockBlob' ], prefixMatch: [ 'backups/db/' ] }
            actions: { baseBlob: { delete: { daysAfterCreationGreaterThan: 30 } } }
          }
        }
        {
          name: 'drills-1-year'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: [ 'blockBlob' ], prefixMatch: [ 'backups/drills/' ] }
            actions: { baseBlob: { delete: { daysAfterCreationGreaterThan: 365 } } }
          }
        }
      ]
    }
  }
}

var common = [
  { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
  { name: 'BACKUP_ACCOUNT_URL', value: storage.properties.primaryEndpoints.blob }
  { name: 'BACKUP_CONTAINER', value: 'backups' }
]

resource exportJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${prefix}-backup'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: { cronExpression: exportCron, parallelism: 1, replicaCompletionCount: 1 }
      replicaTimeout: 3600
      replicaRetryLimit: 1
      registries: [ { server: 'ghcr.io', username: ghcrUsername, passwordSecretRef: 'ghcr-token' } ]
      secrets: [ { name: 'ghcr-token', value: ghcrToken } ]
    }
    template: {
      containers: [
        {
          name: 'ops'
          image: image
          args: [ 'export' ]
          resources: { cpu: json('1'), memory: '2Gi' }
          env: concat(common, [
            { name: 'SOURCE_SERVER', value: '${sql.properties.fullyQualifiedDomainName},1433' }
            { name: 'SOURCE_DATABASE', value: 'cashflow' }
            { name: 'SOURCE_AUTH', value: 'msi' }
          ])
        }
      ]
    }
  }
  dependsOn: [ entraAdmin, backupWriter ]
}

resource drillJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${prefix}-drill'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: { cronExpression: drillCron, parallelism: 1, replicaCompletionCount: 1 }
      replicaTimeout: 3600
      replicaRetryLimit: 0
      registries: [ { server: 'ghcr.io', username: ghcrUsername, passwordSecretRef: 'ghcr-token' } ]
      secrets: [
        { name: 'ghcr-token', value: ghcrToken }
        { name: 'drill-sa-password', value: drillSaPassword }
      ]
    }
    template: {
      containers: [
        {
          name: 'ops'
          image: image
          args: [ 'drill' ]
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(common, [
            { name: 'DRILL_SERVER', value: 'localhost,1433' }
            { name: 'DRILL_DATABASE', value: 'cashflow_restore' }
            { name: 'DRILL_USER', value: 'sa' }
            { name: 'DRILL_PASSWORD', secretRef: 'drill-sa-password' }
            { name: 'DRILL_TRUST_CERT', value: '1' }
            { name: 'DRILL_SHUTDOWN', value: '1' } // stop SQL Server so the job can finish
          ])
        }
        {
          // The scratch database server: only for the drill, deleted with the job's replica.
          name: 'scratch-sql'
          image: 'mcr.microsoft.com/mssql/server:2022-latest'
          resources: { cpu: json('1.5'), memory: '3Gi' }
          env: [
            { name: 'ACCEPT_EULA', value: 'Y' }
            { name: 'MSSQL_PID', value: 'Developer' }
            { name: 'MSSQL_SA_PASSWORD', secretRef: 'drill-sa-password' }
          ]
        }
      ]
    }
  }
  dependsOn: [ backupWriter ]
}

output identityClientId string = identity.properties.clientId
output exportJob string = exportJob.name
output drillJob string = drillJob.name
