-- Cash view per month (F10, ADR-007): only money that moved in or out of the bank accounts.
-- Card purchases are not cash until the card is paid: the payment from the bank counts instead,
-- as card_payments. Transfers between the household's own bank accounts don't count. Excel
-- history rows are already cash-basis and count as they are. Outflows are shown as positive.
CREATE VIEW [mart].[v_monthly_cash] AS
SELECT
    [m].[cash_month],
    [m].[income],
    [m].[expenses],
    [m].[card_payments],
    [m].[savings],
    [m].[debt_payments],
    [m].[net],
    SUM([m].[net]) OVER (ORDER BY [m].[cash_month] ROWS UNBOUNDED PRECEDING) AS [cumulative_net],
    CAST([m].[net] * 1.0 / NULLIF([m].[income], 0) AS DECIMAL(9, 4)) AS [savings_rate],
    [m].[transactions]
FROM (
    SELECT
        [x].[cash_month],
        CAST(SUM(CASE WHEN [x].[bucket] = 'income' THEN [x].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [income],
        CAST(-SUM(CASE WHEN [x].[bucket] = 'expense' THEN [x].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [expenses],
        CAST(-SUM(CASE WHEN [x].[bucket] = 'card_payment' THEN [x].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [card_payments],
        CAST(-SUM(CASE WHEN [x].[bucket] = 'savings' THEN [x].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [savings],
        CAST(-SUM(CASE WHEN [x].[bucket] = 'debt_payment' THEN [x].[amount] ELSE 0 END) AS DECIMAL(19, 4)) AS [debt_payments],
        CAST(SUM([x].[amount]) AS DECIMAL(19, 4)) AS [net],
        COUNT(*) AS [transactions]
    FROM (
        SELECT
            [t].[cash_month],
            [t].[amount],
            CASE
                WHEN [t].[type] = 'income' THEN 'income'
                WHEN [t].[type] IN ('expense', 'fee_interest', 'refund') THEN 'expense'
                WHEN [t].[type] = 'savings' THEN 'savings'
                WHEN [t].[type] = 'debt_payment' THEN 'debt_payment'
                -- A transfer from a bank account to a card: the cash leaves the household now.
                WHEN [t].[type] = 'transfer' AND (
                    [c].[name] = 'Card Payment'
                    OR EXISTS (
                        SELECT 1
                        FROM [core].[transaction] AS [o]
                        JOIN [core].[account] AS [oa]
                            ON [oa].[account_id] = [o].[account_id]
                        WHERE [o].[transfer_group_id] = [t].[transfer_group_id]
                            AND [o].[transaction_id] <> [t].[transaction_id]
                            AND [oa].[kind] = 'credit_card'
                    )
                ) THEN 'card_payment'
                ELSE 'own_transfer'
            END AS [bucket]
        FROM [core].[transaction] AS [t]
        LEFT JOIN [core].[account] AS [a]
            ON [a].[account_id] = [t].[account_id]
        LEFT JOIN [core].[category] AS [c]
            ON [c].[category_id] = [t].[category_id]
        WHERE (
            [t].[source] = 'excel_history'
            OR ([t].[source] <> 'excel_history' AND [a].[kind] IN ('checking', 'savings'))
        )
            -- Months covered by the Excel history keep it (ADR-004, ADR-018).
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
    ) AS [x]
    WHERE [x].[bucket] <> 'own_transfer'
    GROUP BY [x].[cash_month]
) AS [m];
