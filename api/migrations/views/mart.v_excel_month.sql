-- Months where the Cash Flow workbook counts (ADR-004, ADR-018): every month it covers before the
-- "statements from" month in core.app_setting (all of them when that isn't set). From that month on,
-- statements count and the workbook's rows stay only as a reference to check them against.
CREATE VIEW [mart].[v_excel_month] AS
SELECT DISTINCT
    [h].[cash_month]
FROM [core].[transaction] AS [h]
WHERE [h].[source] = 'excel_history'
    AND NOT EXISTS (
        SELECT 1
        FROM [core].[app_setting] AS [s]
        WHERE [s].[setting_key] = 'statements_from'
            AND [h].[cash_month] >= [s].[setting_value]
    );
