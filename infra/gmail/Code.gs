/**
 * household-cashflow: statements by email (F20, ADR-020).
 *
 * Runs in Hernan's Gmail every hour (a Google Apps Script time trigger, on Google's servers). It
 * finds the banks' statement emails, posts each PDF attachment to the app's /api/inbox with the
 * inbox token, and labels the email so it isn't sent again. The app stores the file like an upload
 * and reads it into a batch that waits on the Import page for approval.
 *
 * Labels it adds:
 *   cashflow-imported  sent; read, or a statement already in the app
 *   cashflow-check     sent, but it needs you on the Import page (or the app refused the file)
 *
 * Setup (docs/runbooks/gmail-statements.md): Project Settings -> Script properties APP_URL and
 * INBOX_TOKEN (from infra/azure/setup-inbox.sh), then run setup() once.
 */

// One search per bank. Add a bank by adding its sender (issue #60: Bank of America, Capital One).
const SOURCES = [
  {
    bank: 'Banco Pichincha',
    // Account and credit-card statements; the same sender also emails invoices ("Factura").
    query: 'from:documentoselectronicos@pichincha.com subject:(estado OR estados) -subject:factura',
  },
  { bank: 'PacifiCard', query: 'from:estadodecuenta@pacificard.ec subject:"estado de cuenta"' },
  { bank: 'Diners Club', query: 'from:info@efacturacioninterdin.com subject:"estado de cuenta"' },
];

const DONE = 'cashflow-imported';
const CHECK = 'cashflow-check';
const RECENT = 'newer_than:45d';
const MAX_FILES_PER_RUN = 25; // keeps a run well under Apps Script's 6-minute limit

/** Every hour: statements from the last 45 days that haven't been sent yet. */
function run() {
  importStatements_(RECENT);
}

/**
 * Once, by hand: the backlog since BACKFILL_FROM (a script property, YYYY/MM/DD; default the
 * start of 2026). Run it again until the log says nothing is left; the app skips duplicates.
 */
function backfill() {
  const from = props_().getProperty('BACKFILL_FROM') || '2026/01/01';
  importStatements_('after:' + from);
}

/** Once, by hand: the hourly trigger (replacing any earlier one), then a first run. */
function setup() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'run')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('run').timeBased().everyHours(1).create();
  run();
}

function importStatements_(window) {
  const props = props_();
  const url = (props.getProperty('APP_URL') || '').replace(/\/+$/, '');
  const token = props.getProperty('INBOX_TOKEN') || '';
  if (!url || !token) {
    throw new Error('Set APP_URL and INBOX_TOKEN in Project Settings -> Script properties.');
  }
  const done = label_(DONE);
  const check = label_(CHECK);
  let sent = 0;
  const counts = { read: 0, duplicate: 0, needs_attention: 0, rejected: 0, later: 0 };

  for (const source of SOURCES) {
    const query = `${source.query} has:attachment ${window} -label:${DONE} -label:${CHECK}`;
    for (const thread of GmailApp.search(query, 0, 50)) {
      let finished = true;
      let needsYou = false;
      for (const message of thread.getMessages()) {
        for (const file of message.getAttachments({ includeInlineImages: false })) {
          if (!/\.pdf$/i.test(file.getName())) continue;
          if (sent >= MAX_FILES_PER_RUN) {
            summary_(counts, true);
            return;
          }
          sent += 1;
          const result = post_(url, token, file, message.getFrom());
          if (result === null) {
            finished = false; // the app or its database is asleep: the next run tries again
            counts.later += 1;
            continue;
          }
          counts[result.status] = (counts[result.status] || 0) + 1;
          if (result.status === 'needs_attention' || result.status === 'rejected') needsYou = true;
          console.log(`${source.bank}: ${file.getName()} -> ${result.status}: ${result.message}`);
        }
      }
      if (finished) thread.addLabel(needsYou ? check : done);
    }
  }
  summary_(counts, false);
}

/** Posts one PDF; the app's answer, or null when it can't answer now (asleep, waking up). */
function post_(url, token, file, from) {
  try {
    const response = UrlFetchApp.fetch(`${url}/api/inbox`, {
      method: 'post',
      headers: { Authorization: `Bearer ${token}` },
      payload: {
        file: file.copyBlob().setContentType('application/pdf'),
        sender: address_(from),
      },
      muteHttpExceptions: true,
    });
    const code = response.getResponseCode();
    if (code === 200) return JSON.parse(response.getContentText());
    if (code === 401 || code === 404) {
      throw new Error(`The app refused the token (HTTP ${code}): check INBOX_TOKEN and APP_URL.`);
    }
    console.warn(`${file.getName()}: HTTP ${code}; trying again next run.`);
    return null;
  } catch (e) {
    if (String(e).includes('refused the token')) throw e;
    console.warn(`${file.getName()}: ${e}; trying again next run.`);
    return null;
  }
}

function summary_(counts, more) {
  console.log(
    `Read ${counts.read}, already in the app ${counts.duplicate}, ` +
      `need you on the Import page ${counts.needs_attention}, refused ${counts.rejected}, ` +
      `next run ${counts.later}.${more ? ' More left: run again.' : ''}`
  );
}

/** "Bank <estadodecuenta@bank.ec>" -> "estadodecuenta@bank.ec" */
function address_(from) {
  const m = /<([^>]+)>/.exec(from || '');
  return (m ? m[1] : from || '').trim().toLowerCase();
}

function label_(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}

function props_() {
  return PropertiesService.getScriptProperties();
}
