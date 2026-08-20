targetScope = 'resourceGroup'

@description('Short lowercase prefix; globally unique suffix is added automatically.')
param prefix string = 'asdiligente'
param location string = resourceGroup().location
@secure()
param postgresAdminPassword string
param postgresAdminUser string = 'asistenteadmin'
param appEnv string = 'development'

var suffix = uniqueString(subscription().id, resourceGroup().id)
var storageName = take(toLower('${prefix}${suffix}'), 24)
var apiName = take(toLower('${prefix}-api-${suffix}'), 60)
var planName = '${prefix}-plan'
var postgresName = take(toLower('${prefix}-pg-${suffix}'), 63)
var databaseName = 'asistentediligente'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
  resource web 'blobServices' = {
    name: 'default'
    properties: { deleteRetentionPolicy: { enabled: true, days: 7 } }
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  sku: { name: 'B1', tier: 'Basic' }
  kind: 'linux'
  properties: { reserved: true }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: postgresName
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
  }
}

resource allowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: databaseName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource api 'Microsoft.Web/sites@2023-12-01' = {
  name: apiName
  location: location
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      alwaysOn: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appCommandLine: 'gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app'
      healthCheckPath: '/health'
      appSettings: [
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'APP_ENV', value: appEnv }
        { name: 'DATABASE_URL', value: 'postgresql+psycopg://${postgresAdminUser}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${databaseName}?sslmode=require' }
        { name: 'CORS_ORIGINS', value: storage.properties.primaryEndpoints.web }
      ]
    }
  }
}

output storageAccountName string = storage.name
output staticWebsiteUrl string = storage.properties.primaryEndpoints.web
output apiName string = api.name
output apiUrl string = 'https://${api.properties.defaultHostName}'

