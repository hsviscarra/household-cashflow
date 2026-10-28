-- One row per line that counts as spending (F13, ADR-010): expenses and fees and interest as
-- positive amounts, refunds as negative ones; transfers, income, savings and debt payments left
-- out. Same rules as mart.v_monthly_cashflow: the Excel history wins its months (ADR-004) and a
-- split line counts through its parts (F9).
CREATE VIEW [mart].[v_spending_line] AS
SELECT
    [t].[transaction_id],
    [t].[cash_month],
    [t].[txn_date],
    [t].[source],
    [t].[type],
    CAST(-[t].[amount] AS DECIMAL(19, 4)) AS [amount],
    COALESCE([g].[category_id], [c].[category_id], 0) AS [group_id],
    COALESCE([g].[name], [c].[name], 'Uncategorized') AS [group_name],
    COALESCE([g].[color], [c].[color]) AS [group_color],
    COALESCE([c].[category_id], 0) AS [category_id],
    COALESCE([c].[name], 'Uncategorized') AS [category_name],
    COALESCE([t].[person], 'Joint') AS [person],
    COALESCE([t].[country], [a].[country]) AS [country],
    [t].[is_fixed],
    COALESCE(NULLIF([t].[merchant], ''), [t].[description_raw]) AS [merchant],
    [t].[description_raw] AS [description],
    [t].[account_id],
    [a].[name] AS [account_name]
FROM [core].[transaction] AS [t]
LEFT JOIN [core].[category] AS [c]
    ON [c].[category_id] = [t].[category_id]
LEFT JOIN [core].[category] AS [g]
    ON [g].[category_id] = [c].[parent_id]
LEFT JOIN [core].[account] AS [a]
    ON [a].[account_id] = [t].[account_id]
WHERE [t].[type] IN ('expense', 'fee_interest', 'refund')
    AND NOT (
        [t].[source] = 'statement'
        AND EXISTS (
            SELECT 1
            FROM [core].[transaction] AS [h]
            WHERE [h].[source] = 'excel_history'
                AND [h].[cash_month] = [t].[cash_month]
        )
    )
    AND NOT EXISTS (
        SELECT 1
        FROM [core].[transaction] AS [p]
        WHERE [p].[parent_transaction_id] = [t].[transaction_id]
    );
