-- What borrowing and banking cost per account and month (F14, ADR-011): interest and fees as
-- positive amounts. Interest is the Credit Card Interest category (interest earned on a credit
-- balance reduces it); fees are the rest of Financial Costs (bank fees, SOLCA, the tax on
-- digital services). Same rules as the spending views: the Excel history wins its months
-- (ADR-004, ADR-018) and a split line counts through its parts (F9).
CREATE VIEW [mart].[v_debt_cost] AS
SELECT
    [t].[cash_month],
    [t].[account_id],
    [a].[name] AS [account_name],
    [a].[kind] AS [account_kind],
    CASE WHEN [c].[name] = 'Credit Card Interest' THEN 'interest' ELSE 'fee' END AS [kind],
    COALESCE([c].[name], 'Fees and interest') AS [category_name],
    CAST(-SUM([t].[amount]) AS DECIMAL(19, 4)) AS [amount],
    COUNT(*) AS [transactions]
FROM [core].[transaction] AS [t]
LEFT JOIN [core].[category] AS [c]
    ON [c].[category_id] = [t].[category_id]
LEFT JOIN [core].[category] AS [g]
    ON [g].[category_id] = [c].[parent_id]
LEFT JOIN [core].[account] AS [a]
    ON [a].[account_id] = [t].[account_id]
WHERE (
        [g].[name] = 'Financial Costs'
        OR [c].[name] = 'Financial Costs'
        OR ([t].[type] = 'fee_interest' AND [t].[category_id] IS NULL)
    )
    AND NOT (
        [t].[source] = 'statement'
        AND [t].[cash_month] IN (SELECT [e].[cash_month] FROM [mart].[v_excel_month] AS [e])
    )
    -- From the "statements from" month on (F19), the workbook's rows are a reference only.
    AND NOT (
        [t].[source] = 'excel_history'
        AND [t].[cash_month] NOT IN (SELECT [e].[cash_month] FROM [mart].[v_excel_month] AS [e])
    )
    AND NOT EXISTS (
        SELECT 1
        FROM [core].[transaction] AS [p]
        WHERE [p].[parent_transaction_id] = [t].[transaction_id]
    )
GROUP BY
    [t].[cash_month],
    [t].[account_id],
    [a].[name],
    [a].[kind],
    CASE WHEN [c].[name] = 'Credit Card Interest' THEN 'interest' ELSE 'fee' END,
    COALESCE([c].[name], 'Fees and interest');
