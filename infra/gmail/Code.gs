/**
 * household-cashflow: statements and invoices by email (F20, ADR-020; F21, ADR-021).
 *
 * Runs in Hernan's Gmail once a day, early morning (a Google Apps Script time trigger, on Google's
 * servers). Statements arrive about once a month per bank (Diners around the 5th, Pichincha's card
 * around the 15th, its account between the 13th and 22nd, PacifiCard around the 25th), so a daily
 * look is soon enough; on days with no new email the app isn't contacted at all. It
 * finds the banks' statement emails, posts each PDF attachment to the app's /api/inbox with the
 * inbox token, and labels the email so it isn't sent again. The app stores the file like an upload
 * and reads it into a batch that waits on the Import page for approval.
 *
 * It also sends every electronic invoice XML (SRI "factura", from any vendor: Supermaxi, pharmacy,
 * internet, school...). The app reads its products and matches it to the card line that paid it
 * (Purchases page). Invoices forwarded from another Gmail by a filter count too: a filter keeps the
 * vendor as the sender.
 *
 * And the banks' transfer notices (Produbanco "Transferencia enviada / recibida / acreditada",
 * Pichincha "NOTIFICACION"): their text goes to /api/inbox/transfer, which keeps only the date,
 * amount, account, the other party's name and the description typed at the bank, as a transfer
 * note. When the statement arrives, its anonymous "TRANSFERENCIA" line gets that name (ADR-023).
 *
 * Labels it adds:
 *   cashflow-imported  sent; read, or a statement already in the app
 *   cashflow-check     sent, but it needs you on the Import page (or the app refused the file)
 *
 * Setup (docs/runbooks/gmail-statements.md): Project Settings -> Script properties APP_URL and
 * INBOX_TOKEN (from infra/azure/setup-inbox.sh), then run setup() once.
 */

// One search per bank. Add a bank by adding its sender (issue #60: Bank of America, Capital One).
// `files` picks the attachments to send: statement PDFs, or invoice XMLs.
const PDF = /\.pdf$/i;
const XML = /\.xml$/i;
const SOURCES = [
  {
    bank: 'Banco Pichincha',
    // Account and credit-card statements; the same sender also emails invoices ("Factura").
    query: 'from:documentoselectronicos@pichincha.com subject:(estado OR estados) -subject:factura',
    files: PDF,
  },
  {
    bank: 'PacifiCard',
    query: 'from:estadodecuenta@pacificard.ec subject:"estado de cuenta"',
    files: PDF,
  },
  {
    bank: 'Diners Club',
    query: 'from:info@efacturacioninterdin.com subject:"estado de cuenta"',
    files: PDF,
  },
  {
    bank: 'Produbanco',
    // The Visa ending 5997 ("Estado de Cuenta Produbanco - Grupo Promerica"); the same sender
    // emails transfer and payment notices, which have no statement attached.
    query: 'from:bancaenlinea@produbanco.com subject:"estado de cuenta"',
    files: PDF,
  },
  // Electronic invoices from any vendor: the XML attachment (the PDF next to it is only a copy).
  { bank: 'Invoices', query: 'filename:xml', files: XML },
];

// Transfer notices: text only, no attachment.
const TRANSFERS =
  'from:(bancaenlinea@produbanco.com OR banco@pichincha.com) ' +
  'subject:(transferencia OR notificacion) -subject:"estado de cuenta"';

const DONE = 'cashflow-imported';
const CHECK = 'cashflow-check';
const RECENT = 'newer_than:45d';
const MAX_FILES_PER_RUN = 40;
// Apps Script stops a run at 6 minutes, mid-email, before it can label anything. Stop starting new
// files after 4.5 minutes instead; the next run (or backfill again) picks up where this one left.
const TIME_BUDGET_MS = 4.5 * 60 * 1000;

/** Every day: statements and invoices from the last 45 days that haven't been sent yet. */
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

/** Once, by hand: the daily trigger at about 6 am (replacing any earlier one), then a first run. */
function setup() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'run')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('run').timeBased().everyDays(1).atHour(6).create();
  run();
}

function importStatements_(window) {
  importTransfers_(window);
  importFiles_(window);
}

/** Each transfer notice once; the app answers noted, matched, duplicate or skipped. */
function importTransfers_(window) {
  const props = props_();
  const url = (props.getProperty('APP_URL') || '').replace(/\/+$/, '');
  const token = props.getProperty('INBOX_TOKEN') || '';
  if (!url || !token) {
    throw new Error('Set APP_URL and INBOX_TOKEN in Project Settings -> Script properties.');
  }
  const done = label_(DONE);
  const counts = { noted: 0, matched: 0, duplicate: 0, skipped: 0, later: 0 };
  for (const thread of GmailApp.search(`${TRANSFERS} ${window} -label:${DONE}`, 0, 100)) {
    let finished = true;
    for (const message of thread.getMessages()) {
      const result = postTransfer_(url, token, message);
      if (result === null) {
        finished = false;
        counts.later += 1;
        continue;
      }
      counts[result.status] = (counts[result.status] || 0) + 1;
    }
    if (finished) thread.addLabel(done);
  }
  console.log(
    `Transfer notices: noted ${counts.noted}, matched ${counts.matched}, ` +
      `already noted ${counts.duplicate}, not ours ${counts.skipped}, next run ${counts.later}.`
  );
}

function postTransfer_(url, token, message) {
  try {
    const response = UrlFetchApp.fetch(`${url}/api/inbox/transfer`, {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: `Bearer ${token}` },
      payload: JSON.stringify({
        subject: message.getSubject().slice(0, 300),
        body: message.getPlainBody().slice(0, 100000),
        sender: address_(message.getFrom()),
        sent_on: Utilities.formatDate(message.getDate(), 'America/Guayaquil', 'yyyy-MM-dd'),
      }),
      muteHttpExceptions: true,
    });
    const code = response.getResponseCode();
    if (code === 200) return JSON.parse(response.getContentText());
    if (code === 401 || code === 404) {
      throw new Error(`The app refused the token (HTTP ${code}): check INBOX_TOKEN and APP_URL.`);
    }
    console.warn(`Transfer notice: HTTP ${code}; trying again next run.`);
    return null;
  } catch (e) {
    if (String(e).includes('refused the token')) throw e;
    console.warn(`Transfer notice: ${e}; trying again next run.`);
    return null;
  }
}

function importFiles_(window) {
  const props = props_();
  const url = (props.getProperty('APP_URL') || '').replace(/\/+$/, '');
  const token = props.getProperty('INBOX_TOKEN') || '';
  if (!url || !token) {
    throw new Error('Set APP_URL and INBOX_TOKEN in Project Settings -> Script properties.');
  }
  const started = Date.now();
  const done = label_(DONE);
  const check = label_(CHECK);
  let sent = 0;
  const counts = { read: 0, duplicate: 0, skipped: 0, needs_attention: 0, rejected: 0, later: 0 };

  for (const source of SOURCES) {
    const query = `${source.query} has:attachment ${window} -label:${DONE} -label:${CHECK}`;
    for (const thread of GmailApp.search(query, 0, 50)) {
      let finished = true;
      let needsYou = false;
      for (const message of thread.getMessages()) {
        for (const file of message.getAttachments({ includeInlineImages: false })) {
          if (!source.files.test(file.getName())) continue;
          if (sent >= MAX_FILES_PER_RUN || Date.now() - started > TIME_BUDGET_MS) {
            summary_(counts, true);
            return;
          }
          sent += 1;
          const result = post_(url, token, file, message.getFrom());
          if (result === null) {
            finished = false; // the app couldn't answer: tomorrow's run tries again
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

/** Posts one file; the app's answer, or null when it can't answer now (asleep, waking up). */
function post_(url, token, file, from) {
  try {
    const response = UrlFetchApp.fetch(`${url}/api/inbox`, {
      method: 'post',
      headers: { Authorization: `Bearer ${token}` },
      payload: {
        file: file
          .copyBlob()
          .setContentType(XML.test(file.getName()) ? 'application/xml' : 'application/pdf'),
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
    `Read ${counts.read}, already in the app ${counts.duplicate}, not an invoice ${counts.skipped}, ` +
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
