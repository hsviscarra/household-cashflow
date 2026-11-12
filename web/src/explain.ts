// What each number in the app means (ADR-073), written once: every ⓘ reads from here.

export type Explanation = { title: string; what: string; how?: string; excludes?: string };

export const EXPLAIN = {
  money_in: {
    title: "Money in",
    what: "Salaries, rent and any other income.",
    how: "Income lines of the month. A salary counts in the month it pays for: paid on the 15th or later, it is the next month's.",
    excludes: "Transfers between your own accounts and refunds.",
  },
  spent: {
    title: "Spent",
    what: "Purchases, bills, fees and interest, less refunds.",
    how: "Card purchases count on the day you buy. Paying the card later doesn't count again.",
    excludes: "Savings, investing, the new house and loan payments: those are Set aside.",
  },
  set_aside: {
    title: "Set aside",
    what: "Money you still have, in another form: savings, investing, the new house and loan payments.",
    how: "Lines in savings and debt-payment categories.",
  },
  free_cash: {
    title: "Free cash",
    what: "What was there to set aside: money in minus spent.",
  },
  left_over: {
    title: "Left over",
    what: "What stayed in the bank accounts: free cash minus set aside.",
    how: "Money in − spent − set aside. It was called “Kept” before.",
  },
  same_days: {
    title: "Compared with",
    what: "A month still running is compared with the same days of the month before; a finished month with the whole month before.",
  },
  money_now: {
    title: "Your money now",
    what: "Each account's balance as the bank shows it.",
    how: "Bank sync's balance for Capital One and Bank of America; for the others, the closing balance of the last statement loaded. Each says its date.",
    excludes: "Lauren's flexible savings until it is added as an account.",
  },
  net_worth: {
    title: "Net worth",
    what: "What you own minus what you owe.",
    how: "Bank balances, investments, properties, the car and what's paid of the new house, minus loans, cards and what you owe people.",
    excludes: "What is still to pay on the new house (a commitment, not a debt yet).",
  },
  investments: {
    title: "Investments",
    what: "The Interactive Brokers account: value, gain since bought, and positions.",
    how: "Read every weekday from Interactive Brokers.",
  },
  budget: {
    title: "Budget",
    what: "What you planned to spend by group this month, what you spent, and whether you're on pace for this day of the month.",
  },
  goals: {
    title: "Goals",
    what: "Each goal's progress, what's needed each month to reach it on time, and whether you're on pace.",
  },
  coming_up: {
    title: "Coming up",
    what: "Bills and installments due in the next 14 days, and the lowest your bank accounts are expected to reach.",
    how: "From your bills, salaries and usual spending (the Forecast page).",
  },
  committed: {
    title: "Committed this month",
    what: "The total of every bill, subscription and loan payment due this month, paid or not: money already promised before day-to-day spending.",
  },
  commitments: {
    title: "Commitments",
    what: "What is still to pay on a purchase in progress, such as the new house. Not a debt yet; it becomes one only if you sign a loan.",
  },
  lowest_cash: {
    title: "Lowest cash ahead",
    what: "The lowest your bank accounts are expected to reach in the next 12 months, and on what day.",
    how: "From your bills, salaries and usual spending.",
  },
  sources: {
    title: "Where each account stands",
    what: "How each account's data arrives (bank sync, email, or you upload), the day it covers through, and what happens next.",
  },
} satisfies Record<string, Explanation>;

export type ExplainKey = keyof typeof EXPLAIN;
