-- Amount per month, type and category with its group, for breakdowns and charts.
-- Outflows are shown as positive amounts, income as positive; transfers excluded.
CREATE VIEW [mart].[v_category_month] AS
SELECT
    [t].[cash_month],
    [t].[type],
    COALESCE([g].[category_id], [c].[category_id], 0) AS [group_id],
    COALESCE([g].[name], [c].[name], 'Uncategorized') AS [group_name],
    COALESCE([g].[color], [c].[color]) AS [group_color],
    COALESCE([c].[category_id], 0) AS [category_id],
    COALESCE([c].[name], 'Uncategorized') AS [category_name],
    CAST(SUM(CASE WHEN [t].[type] = 'income' THEN [t].[amount] ELSE -[t].[amount] END) AS DECIMAL(19, 4)) AS [amount],
    COUNT(*) AS [transactions]
FROM [core].[transaction] AS [t]
LEFT JOIN [core].[category] AS [c]
    ON [c].[category_id] = [t].[category_id]
LEFT JOIN [core].[category] AS [g]
    ON [g].[category_id] = [c].[parent_id]
WHERE [t].[type] <> 'transfer'
    -- Months covered by the Excel history keep it; statement lines count from the first month
    -- without history, so a month is never counted twice (ADR-004).
    AND NOT (
        [t].[source] = 'statement'
        AND EXISTS (
            SELECT 1
            FROM [core].[transaction] AS [h]
            WHERE [h].[source] = 'excel_history'
                AND [h].[cash_month] = [t].[cash_month]
        )
    )
GROUP BY
    [t].[cash_month],
    [t].[type],
    COALESCE([g].[category_id], [c].[category_id], 0),
    COALESCE([g].[name], [c].[name], 'Uncategorized'),
    COALESCE([g].[color], [c].[color]),
    COALESCE([c].[category_id], 0),
    COALESCE([c].[name], 'Uncategorized');
