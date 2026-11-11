// Cost guard for the whole subscription (ADR-076): a $20 monthly budget that emails, in case
// something outside rg-cashflow starts costing money, and Azure's free cost anomaly alert, which
// emails when a day's spend jumps against the usual pattern. No kill switch here: stopping the app
// wouldn't help with a cost somewhere else. Deployed by setup-cost-guard.sh.
targetScope = 'subscription'

param prefix string = 'cashflow'

@description('Who gets the emails.')
param alertEmail string

@description('Monthly cap in USD.')
param amount int = 20

param budgetStartDate string = utcNow('yyyy-MM-01')
param today string = utcNow('yyyy-MM-dd')

var email = [alertEmail]

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: '${prefix}-subscription-budget'
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actualOver50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        contactEmails: email
        thresholdType: 'Actual'
      }
      actualOver100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: email
        thresholdType: 'Actual'
      }
      forecastOver100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: email
        thresholdType: 'Forecasted'
      }
    }
  }
}

resource anomaly 'Microsoft.CostManagement/scheduledActions@2023-11-01' = {
  name: '${prefix}-cost-anomaly'
  kind: 'InsightAlert'
  properties: {
    displayName: 'Cost anomaly in the subscription'
    status: 'Enabled'
    viewId: subscriptionResourceId('Microsoft.CostManagement/views', 'ms:DailyAnomalyByResourceGroup')
    notificationEmail: alertEmail
    notification: {
      to: email
      subject: 'Azure: unusual spend in the subscription'
    }
    schedule: {
      frequency: 'Daily'
      startDate: '${today}T00:00:00Z'
      endDate: dateTimeAdd('${today}T00:00:00Z', 'P1Y')
    }
  }
}
