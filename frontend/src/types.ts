export type Section = 'profitability' | 'competition' | 'demand' | 'rent' | 'location';
export type Area = {
  code: string; name: string; district: string; administrative_dong: string; category: string;
  latitude: number; longitude: number; area_m2: number; radius_m: number;
};
export type Metrics = {
  total_sales_krw: number | null; store_count: number; transaction_count: number | null;
  average_sales_krw: number | null; transactions_per_store: number | null; average_payment_krw: number | null;
  sales_yoy_pct: number | null; stores_yoy_pct: number | null; average_sales_yoy_pct: number | null;
  transactions_yoy_pct: number | null;
  competition_type: string;
};
export type Rental = {
  id: string; area_code: string; title: string; latitude: number; longitude: number;
  monthly_rent_krw: number | null; deposit_krw: number | null; area_m2: number | null;
  floor: string | null; maintenance_fee_krw: number | null; observed_at: string; source_url: string | null;
  source_name: string | null; is_transfer: boolean; is_demo: boolean;
};
export type MenuItem = { name: string; price_krw: number | null; source_url: string | null; source_date: string | null };
export type BrandMenuItem = MenuItem & { channel: 'official_menu' | 'gift_catalog' };
export type Store = {
  id: string; name: string; latitude: number; longitude: number; distance_m: number | null;
  menu: MenuItem[]; observed_at: string; source_url: string | null; address: string | null; brand: string | null;
};
export type Observation = { quarter: string; total_sales_krw: number | null; store_count: number; transaction_count: number | null;
  average_sales_krw: number | null; sales_yoy_pct: number | null; stores_yoy_pct: number | null };
export type ComparisonItem = { area: Area; metrics: Metrics | null; rentals: Rental[]; missing_reason: string | null; observations: Observation[] };
export type Meta = { data_mode: string; data_version: string; quarter: string; warning: string };
export type Comparison = { meta: Meta; items: ComparisonItem[] };
export type Bin = { label: string; value: number | null; share_pct: number | null };
export type Distribution = { unit: string; age_basis: string; weekday_basis: string; time_basis: string; age: Bin[]; weekday: Bin[]; time: Bin[] };
export type Detail = {
  meta: Meta; area: Area; current: Metrics | null; observations: Observation[];
  forecast: { model_version: string; interval_method: string; coverage_validated: boolean; points: {
    quarter: string; total_sales_krw: number | null; average_sales_krw: number | null; sales_yoy_pct: number | null; stores_yoy_pct: number | null;
    lower80_krw: number | null; upper80_krw: number | null; lower90_krw: number | null; upper90_krw: number | null;
  }[] } | null;
  demand: Record<string, Distribution>; rentals: Rental[]; stores: Store[]; missing_reason: string | null;
};
export type Explanation = {
  status: 'completed' | 'running' | 'disabled' | 'unavailable' | 'failed'; cache_key: string; cache_hit: boolean;
  message: string | null; retry_after_seconds: number | null; prompt_version: string; model: string | null;
  content: { summary: string; blocks: { title: string; text: string; evidence_ids: string[] }[]; caveats: string[] } | null;
  evidence: { facts?: Record<string, unknown> };
};
export type Config = { data_mode: string; llm_enabled: boolean; llm_auth_required: boolean; demo_area_codes: string[]; quarters: string[] };
