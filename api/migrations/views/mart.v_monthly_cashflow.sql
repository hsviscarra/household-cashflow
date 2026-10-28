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
        -- Months covered by the Excel history keep it; statement lines count from the first
        -- month without history, so a month is never counted twice (ADR-004, ADR-018).
        AND NOT (
            [t].[source] = 'statement'
            AND [t].[cash_month] IN (SELECT [e].[cash_month] FROM [mart].[v_excel_month] AS [e])
        )
        -- From the "statements from" month on (F19), the workbook's rows are a reference only.
        AND NOT (
            [t].[source] = 'excel_history'
            AND [t].[cash_month] NOT IN (SELECT [e].[cash_month] FROM [mart].[v_excel_month] AS [e])
        )
        -- A line split into parts (F9) counts through its parts only.
        AND NOT EXISTS (
            SELECT 1
            FROM [core].[transaction] AS [p]
            WHERE [p].[parent_transaction_id] = [t].[transaction_id]
        )
    GROUP BY [t].[cash_month]
) AS [m];
