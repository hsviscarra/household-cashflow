-- Cash view per month: money in and out of the household, transfers between own accounts excluded.
-- Outflows are shown as positive amounts; net = income - expenses - savings - debt payments.
CREATE VIEW [mart].[v_monthly_cashflow] AS
SELECT
    [m].[cash_month],
    [m].[income],
    [m].[expenses],
    [m].[savings],
    [m].[debt_payments],
    [m].[net],
    SUM([m].[net]) OVER (ORDER BY [m].[cash_month] ROWS UNBOUNDED PRECEDING) AS [cumulative_net],
    CAST([m].[net] * 1.0 / NULLIF([m].[income], 0) AS DECIMAL(9, 4)) AS [savings_rate],
    [m].[transactions]
FROM (
    SELECT
        [t].[cash_month],
        CAST(SUM(CASE WHEN [t].[type] = 'income' THEN [t].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [income],
        CAST(-SUM(CASE WHEN [t].[type] IN ('expense', 'fee_interest', 'refund') THEN [t].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [expenses],
        CAST(-SUM(CASE WHEN [t].[type] = 'savings' THEN [t].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [savings],
        CAST(-SUM(CASE WHEN [t].[type] = 'debt_payment' THEN [t].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [debt_payments],
        CAST(SUM([t].[amount]) AS DECIMAL(19, 4)) AS [net],
        COUNT(*) AS [transactions]
    FROM [core].[transaction] AS [t]
    WHERE [t].[type] <> 'transfer'
    GROUP BY [t].[cash_month]
) AS [m];
