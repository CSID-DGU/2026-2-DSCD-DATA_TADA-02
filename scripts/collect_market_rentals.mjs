// Read documented public listing pages and retain factual address and rental fields.
import fs from 'node:fs';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const userAgent = 'DATATADA-RentCollector/1.0';
const [outputArgument, name = 'ddak'] = process.argv.slice(2);
const sites = { ddak: 'https://ddak.disco.re', heybd: 'https://www.heybd.co.kr' };
const origin = sites[name];
if (!outputArgument || !origin) throw new Error('Pass a checkpoint directory and ddak or heybd');
const output = path.resolve(outputArgument);
fs.mkdirSync(output, { recursive: true });
const recordsPath = path.join(output, `${name}_records.jsonl`);
const summaryPath = path.join(output, `${name}_summary.json`);
const json = (value) => JSON.stringify(value).replaceAll('\u00b7', '\\u00b7');
const asText = (html = '') => html.replace(/<[^>]+>/g, '')
  .replace(/&#(\d+);/g, (_, number) => String.fromCodePoint(Number(number)))
  .replace(/&#x([\da-f]+);/gi, (_, number) => String.fromCodePoint(parseInt(number, 16)))
  .replaceAll('&nbsp;', ' ').replaceAll('&amp;', '&').replace(/\s+/g, ' ').trim();

let nextRequest = 0;
let stopped = null;
async function request(url) {
  const scheduled = Math.max(Date.now(), nextRequest);
  nextRequest = scheduled + 350;
  await delay(Math.max(0, scheduled - Date.now()));
  if (stopped) throw new Error(stopped);
  const response = await fetch(url, {
    headers: { 'User-Agent': userAgent }, redirect: 'manual', signal: AbortSignal.timeout(25000),
  });
  if ([401, 403, 429].includes(response.status)) {
    stopped = `HTTP ${response.status} from public source`;
    await response.body?.cancel();
    throw new Error(stopped);
  }
  return { status: response.status, body: await response.text() };
}

function won(value = '') {
  const raw = asText(value).replace(/[\s,]/g, '');
  if (/^\d+원$/.test(raw)) return Number(raw.slice(0, -1));
  const cleaned = raw.replace(/억원$/, '억').replace(/(?:만원|만)$/, '');
  const match = cleaned.match(/^(?:(\d+(?:\.\d+)?)억(?:(\d+(?:\.\d+)?))?|(\d+(?:\.\d+)?))$/);
  if (!match) return null;
  const inManwon = match[1] ? Number(match[1]) * 10_000 + Number(match[2] ?? 0) : Number(match[3]);
  return Math.round(inManwon * 10_000);
}

function publicMarker(html, id, address) {
  let stream = '';
  for (const match of html.matchAll(/self\.__next_f\.push\((\[.*?\])\)<\/script>/gs)) {
    try {
      const [, payload] = JSON.parse(match[1]);
      if (typeof payload === 'string') stream += payload;
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
    }
  }
  const points = new Map();
  function walk(value) {
    if (!value || typeof value !== 'object') return;
    if ((value.property_id === id || value.id === id || value.id === `prop:${id}`)
        && value.address_open === true && asText(value.address ?? '') === address
        && Number.isFinite(value.latitude) && Number.isFinite(value.longitude)) {
      points.set(`${value.latitude},${value.longitude}`, {
        latitude: value.latitude, longitude: value.longitude,
      });
    }
    Object.values(value).forEach(walk);
  }
  for (const line of stream.split('\n')) {
    try {
      walk(JSON.parse(line.slice(line.indexOf(':') + 1)));
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
    }
  }
  return points.size === 1 ? points.values().next().value : {};
}

function extractDdak(html, id) {
  const labels = new Map();
  for (const match of html.matchAll(/<dt[^>]*>([\s\S]*?)<\/dt>\s*<dd[^>]*>([\s\S]*?)<\/dd>/g)) {
    const label = asText(match[1]);
    if (!labels.has(label)) labels.set(label, asText(match[2]));
  }
  if (!labels.has('거래형태') && !labels.has('보증금/월세')) return { status: 'detail_unavailable' };
  const address = asText(html.match(/<p[^>]*>\s*((?:서울특별시|서울시|서울)\s+[^<>]{1,180})\s*<\/p>/)?.[1]);
  if (!address) return { status: 'seoul_address_not_observed' };
  const trade = labels.get('거래형태') ?? '';
  if (/^(?:매매|전세)$/.test(trade)) return { status: 'other_transaction' };
  const [depositText, rentText] = (labels.get('보증금/월세') ?? '').split('/');
  const deposit = won(depositText) ?? won(labels.get('보증금'));
  const rent = won(rentText) ?? won(labels.get('월세'));
  return {
    status: 'seoul_listing', address, trade_type: trade, deposit_krw: deposit,
    monthly_rent_krw: rent > 0 ? rent : null, floor_raw: labels.get('층수') ?? '',
    area_pyeong_raw: '', area_raw: labels.get('전용면적') ?? labels.get('전체면적') ?? '',
    ...publicMarker(html, id, address),
  };
}

function extractHeybd(html) {
  const field = (key) => asText(html.match(new RegExp(`data-testid="listing-detail-${key}"[^>]*>([^<]*)`))?.[1]);
  const kind = field('kind');
  const rental = field('rental-type');
  if (!kind || !rental) return { status: 'detail_unavailable' };
  if (kind !== '상가' || !['월세', '반전세'].includes(rental)) return { status: 'other_transaction' };
  const meta = html.match(/<meta\s+name="description"\s+content="([^"]*)"/)?.[1] ?? '';
  const description = asText(meta).split('\u00b7').map((part) => part.trim());
  const address = description.find((part) => /^서울(?:특별시|시)?\s+\S+구/.test(part));
  if (!address) return { status: 'seoul_address_not_observed' };
  const details = description[0].match(/^보증금\s*(.*?)\s*\/\s*월세\s*(.*)$/);
  const rent = won(details?.[2]);
  return { status: 'seoul_listing', address, trade_type: rental, deposit_krw: won(details?.[1]),
    monthly_rent_krw: rent > 0 ? rent : null, floor_raw: '', area_raw: description[1] ?? '' };
}

async function ddakIndex() {
  const sitemap = await request(`${origin}/sitemap.xml`);
  if (sitemap.status !== 200) throw new Error('Could not read the public sitemap');
  return [...new Set([...sitemap.body.matchAll(/<loc>(https:\/\/ddak\.disco\.re\/properties\/[0-9a-f-]{36})<\/loc>/g)]
    .map((match) => match[1]))];
}

async function heybdIndex() {
  const initial = `${origin}/listings?${new URLSearchParams({ kind: '상가', sort: 'latest' })}`;
  const queue = [initial];
  const pages = new Set([0]);
  const urls = new Set();
  for (let index = 0; index < queue.length; index += 1) {
    const result = await request(queue[index]);
    if (result.status !== 200) throw new Error('Could not read the public shop listing page');
    for (const match of result.body.matchAll(/href="(\/listings(?:\?[^"\s]+|\/[0-9a-f-]{36}))"/g)) {
      const link = new URL(match[1].replaceAll('&amp;', '&'), origin);
      if (/^\/listings\/[0-9a-f-]{36}$/.test(link.pathname)) {
        urls.add(link.href);
      } else if (link.searchParams.get('kind') === '상가' && link.searchParams.get('sort') === 'latest'
          && [...link.searchParams.keys()].every((key) => ['page', 'kind', 'sort'].includes(key))) {
        const page = Number(link.searchParams.get('page') ?? 0);
        if (Number.isInteger(page) && page > 0 && !pages.has(page)) {
          if (page > 200) throw new Error('Unexpected shop listing pagination');
          pages.add(page);
          queue.push(link.href);
        }
      }
    }
  }
  console.log(`heybd: ${queue.length} public shop index pages`);
  return [...urls];
}

const robots = await request(`${origin}/robots.txt`);
if (robots.status !== 200 || !/^Allow:\s*\/\s*$/mi.test(robots.body)
    || /^Disallow:\s*\/(?:properties(?:[/?*].*)?|listings(?:[/?*].*)?)?\s*$/mi.test(robots.body)) {
  throw new Error('Public listing paths are not confirmed by robots.txt');
}
const urls = await (name === 'ddak' ? ddakIndex() : heybdIndex());
if (urls.length === 0) throw new Error('No public listing paths found');
const fresh = new Set(urls);
fs.writeFileSync(path.join(output, `${name}_index.json`), `${json(urls)}\n`, 'utf8');
const existing = fs.existsSync(recordsPath) ? fs.readFileSync(recordsPath, 'utf8').split('\n') : [];
const records = new Map();
for (const line of existing.filter(Boolean)) {
  const value = JSON.parse(line);
  if (fresh.has(value.source_url) && value.status !== 'request_error') records.set(value.source_url, value);
}
const pending = urls.filter((url) => !records.has(url));
let next = 0;
let errors = 0;
let consecutiveErrors = 0;
console.log(`${name}: ${urls.length} public pages, ${records.size} already processed in this checkpoint`);

async function requestDetail(url) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const response = await request(url);
      if ([500, 502, 503, 504].includes(response.status)) throw new Error(`HTTP ${response.status}`);
      return response;
    } catch (error) {
      if (stopped || attempt === 1) throw error;
      // Hold new requests to this host briefly before retrying transient errors.
      nextRequest = Math.max(nextRequest, Date.now() + 1500);
      await delay(1500);
    }
  }
}

async function worker() {
  while (next < pending.length && !stopped) {
    const sourceUrl = pending[next++];
    const id = sourceUrl.split('/').at(-1);
    const selectedUrl = name === 'ddak'
      ? `${origin}/properties?${new URLSearchParams({ selected: `prop:${id}` })}` : sourceUrl;
    let result;
    try {
      const page = await requestDetail(selectedUrl);
      if (page.status === 200) {
        if (/verify you are human|cf-chl-|captcha challenge/i.test(page.body) && !/<dt\b/.test(page.body)) {
          stopped = 'Access challenge from public source';
          throw new Error(stopped);
        }
        result = name === 'ddak' ? extractDdak(page.body, id) : extractHeybd(page.body);
      } else if (page.status === 404 || page.status === 410) {
        result = { status: 'detail_unavailable' };
      } else {
        throw new Error(`HTTP ${page.status}`);
      }
      consecutiveErrors = 0;
    } catch (error) {
      const reason = error.cause?.code ?? error.message;
      result = { status: 'request_error', reason };
      errors += 1;
      consecutiveErrors += 1;
      if (consecutiveErrors >= 5) stopped ??= `Five consecutive transport or detail errors: ${reason}`;
    }
    const row = { source_url: sourceUrl, source_listing_id: id, checked_at: new Date().toISOString(), ...result };
    fs.appendFileSync(recordsPath, `${json(row)}\n`, 'utf8');
    if (result.status !== 'request_error') records.set(sourceUrl, row);
    if (records.size % 100 === 0) console.log(`${name}: ${records.size}/${urls.length} pages processed`);
  }
}

await Promise.all([worker(), worker()]);
const counts = {};
for (const row of records.values()) counts[row.status] = (counts[row.status] ?? 0) + 1;
const summary = { urls: urls.length, processed: records.size, counts, errors, stopped,
  complete: urls.length === records.size && !stopped };
fs.writeFileSync(summaryPath, `${json(summary)}\n`, 'utf8');
console.log(json(summary));
if (!summary.complete) process.exitCode = 2;
