-- =============================================================================
-- Modellbahn-Shop · Zielmodell aller Module (Referenz, keine Migration)
-- =============================================================================
-- Stand: 22.10.2026. Geprüft gegen PostgreSQL 17 mit gegentests.sql:
-- 46 Tabellen, 203 CHECK-/FK-/UNIQUE-Regeln, 35 Gegentests und 3 Positivtests.
-- Kein Fremdschlüssel löscht kaskadierend über eine Modulgrenze.
--
-- Jeder Schritt des Fahrplans leitet seine Alembic-Migration aus dem passenden
-- Ausschnitt ab. Weicht eine Migration bewusst ab, wird diese Datei mitgezogen.
-- Die Vorgaben für IDs (UUIDv7 aus dem Code) und Zeitstempel stehen in KONZEPT.md §5.1;
-- die DEFAULT-Werte hier dienen nur dem bequemen Befüllen beim Prüfen.
-- =============================================================================

-- Interne Validierung des Datenmodells v2 (kein Liefergegenstand).
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS ltree;

CREATE SCHEMA identity; CREATE SCHEMA catalog; CREATE SCHEMA media; CREATE SCHEMA manufacturing;
CREATE SCHEMA inventory; CREATE SCHEMA sales; CREATE SCHEMA planning; CREATE SCHEMA ai; CREATE SCHEMA platform;

-- identity ---------------------------------------------------------------
CREATE TABLE identity.accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('staff','customer')),
  email citext NOT NULL, display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
  password_hash text NOT NULL, role text CHECK (role IN ('owner','staff','packer')),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','deleted')),
  email_verified_at timestamptz, failed_login_count smallint NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
  locked_until timestamptz, last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), version integer NOT NULL DEFAULT 1,
  UNIQUE (kind, email), UNIQUE (id, kind), CHECK ((kind = 'staff') = (role IS NOT NULL)));
CREATE TABLE identity.sessions (
  token_hash char(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  account_id uuid NOT NULL, kind text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL DEFAULT now(), user_agent text,
  CHECK (expires_at > created_at),
  FOREIGN KEY (account_id, kind) REFERENCES identity.accounts (id, kind) ON DELETE CASCADE);
CREATE TABLE identity.account_tokens (
  token_hash char(64) PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  account_id uuid NOT NULL REFERENCES identity.accounts ON DELETE CASCADE,
  purpose text NOT NULL CHECK (purpose IN ('verify_email','reset_password')),
  created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL, used_at timestamptz, source_event_id uuid UNIQUE,
  CHECK (expires_at > created_at));

-- media ------------------------------------------------------------------
CREATE TABLE media.assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('image','model_3d')),
  status text NOT NULL DEFAULT 'pending_upload'
    CHECK (status IN ('pending_upload','uploaded','processing','ready','failed','rejected')),
  original_key text NOT NULL UNIQUE, original_filename text NOT NULL, mime_type text NOT NULL,
  size_bytes bigint CHECK (size_bytes > 0), sha256 char(64) CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  attempts smallint NOT NULL DEFAULT 0, last_error text,
  uploaded_by uuid REFERENCES identity.accounts ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz,
  UNIQUE (id, kind),
  CHECK (status IN ('pending_upload') OR (size_bytes IS NOT NULL AND sha256 IS NOT NULL)));
CREATE UNIQUE INDEX assets_dedupe ON media.assets (kind, sha256) WHERE status <> 'rejected';
CREATE TABLE media.image_details (
  asset_id uuid PRIMARY KEY, kind text NOT NULL DEFAULT 'image' CHECK (kind = 'image'),
  width_px int NOT NULL CHECK (width_px > 0), height_px int NOT NULL CHECK (height_px > 0),
  dominant_color char(7) CHECK (dominant_color ~ '^#[0-9a-f]{6}$'), lqip text, phash bigint,
  FOREIGN KEY (asset_id, kind) REFERENCES media.assets (id, kind) ON DELETE CASCADE);
CREATE TABLE media.renditions (
  asset_id uuid NOT NULL, kind text NOT NULL DEFAULT 'image' CHECK (kind = 'image'),
  name text NOT NULL CHECK (name IN ('thumb','sm','md','lg','xl','og')),
  format text NOT NULL CHECK (format IN ('webp','avif','jpeg')),
  width_px int NOT NULL, height_px int NOT NULL, size_bytes int NOT NULL, storage_key text NOT NULL UNIQUE,
  PRIMARY KEY (asset_id, name, format),
  FOREIGN KEY (asset_id, kind) REFERENCES media.assets (id, kind) ON DELETE CASCADE);
CREATE TABLE media.model_details (
  asset_id uuid PRIMARY KEY, kind text NOT NULL DEFAULT 'model_3d' CHECK (kind = 'model_3d'),
  format text NOT NULL CHECK (format IN ('stl','3mf','obj')),
  triangle_count int, bbox_x_mm numeric(8,2), bbox_y_mm numeric(8,2), bbox_z_mm numeric(8,2),
  volume_mm3 numeric(12,1), surface_mm2 numeric(12,1), is_watertight boolean,
  preview_asset_id uuid, preview_kind text NOT NULL DEFAULT 'image' CHECK (preview_kind = 'image'),
  FOREIGN KEY (asset_id, kind) REFERENCES media.assets (id, kind) ON DELETE CASCADE,
  FOREIGN KEY (preview_asset_id, preview_kind) REFERENCES media.assets (id, kind) ON DELETE SET NULL (preview_asset_id));

-- catalog ----------------------------------------------------------------
CREATE TABLE catalog.scales (code text PRIMARY KEY, name text NOT NULL, ratio smallint NOT NULL, gauge_mm numeric(4,1) NOT NULL);
CREATE TABLE catalog.epochs (code text PRIMARY KEY CHECK (code IN ('I','II','III','IV','V','VI')), from_year smallint NOT NULL, to_year smallint);
CREATE TABLE catalog.finishes (code text PRIMARY KEY, name text NOT NULL, surcharge_pct smallint NOT NULL DEFAULT 0, extra_days smallint NOT NULL DEFAULT 0);
CREATE TABLE catalog.categories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), parent_id uuid REFERENCES catalog.categories ON DELETE RESTRICT,
  slug text NOT NULL UNIQUE, name text NOT NULL, sort_order smallint NOT NULL DEFAULT 0);
CREATE TABLE catalog.products (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), slug text NOT NULL UNIQUE, name text NOT NULL,
  primary_category_id uuid NOT NULL REFERENCES catalog.categories ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived')),
  prototype jsonb NOT NULL DEFAULT '{}', short_description text, description_md text,
  seo_title text CHECK (char_length(seo_title) <= 60), seo_description text CHECK (char_length(seo_description) <= 155),
  search_vector tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('german', coalesce(name,'')),'A') || setweight(to_tsvector('german', coalesce(short_description,'')),'B')) STORED,
  version int NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE catalog.product_categories (product_id uuid REFERENCES catalog.products ON DELETE CASCADE, category_id uuid REFERENCES catalog.categories ON DELETE RESTRICT, PRIMARY KEY (product_id, category_id));
CREATE TABLE catalog.product_epochs (product_id uuid REFERENCES catalog.products ON DELETE CASCADE, epoch_code text REFERENCES catalog.epochs, PRIMARY KEY (product_id, epoch_code));
CREATE TABLE catalog.product_scales (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_id uuid NOT NULL REFERENCES catalog.products ON DELETE CASCADE,
  scale_code text NOT NULL REFERENCES catalog.scales, length_mm numeric(7,1), width_mm numeric(7,1), height_mm numeric(7,1), weight_g int,
  UNIQUE (product_id, scale_code), UNIQUE (id, scale_code));
CREATE TABLE catalog.variants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_scale_id uuid NOT NULL REFERENCES catalog.product_scales ON DELETE CASCADE,
  finish_code text NOT NULL REFERENCES catalog.finishes, sku text NOT NULL UNIQUE,
  gtin char(13) UNIQUE CHECK (gtin ~ '^[0-9]{13}$'),
  price_cents int NOT NULL CHECK (price_cents >= 0), compare_at_cents int CHECK (compare_at_cents > price_cents),
  vat_rate_bp smallint NOT NULL DEFAULT 1900, allow_backorder boolean NOT NULL DEFAULT true, is_active boolean NOT NULL DEFAULT true,
  UNIQUE (product_scale_id, finish_code));
CREATE TABLE catalog.product_media (
  product_id uuid NOT NULL REFERENCES catalog.products ON DELETE CASCADE,
  asset_id uuid NOT NULL, asset_kind text NOT NULL DEFAULT 'image' CHECK (asset_kind = 'image'),
  position smallint NOT NULL, role text NOT NULL DEFAULT 'gallery' CHECK (role IN ('gallery','detail','scale_comparison','packaging')),
  scale_code text REFERENCES catalog.scales, finish_code text REFERENCES catalog.finishes, alt_text text,
  PRIMARY KEY (product_id, asset_id),
  UNIQUE (product_id, position) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (asset_id, asset_kind) REFERENCES media.assets (id, kind) ON DELETE RESTRICT);
CREATE TABLE catalog.product_copy_revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_id uuid NOT NULL REFERENCES catalog.products ON DELETE CASCADE,
  revision int NOT NULL, source text NOT NULL CHECK (source IN ('human','ai')), ai_run_id uuid, fields jsonb NOT NULL,
  created_by uuid REFERENCES identity.accounts ON DELETE SET NULL, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (product_id, revision), CHECK (source = 'human' OR ai_run_id IS NOT NULL));

-- manufacturing ----------------------------------------------------------
CREATE TABLE manufacturing.materials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL UNIQUE,
  technology text NOT NULL CHECK (technology IN ('fdm','resin')), unit text NOT NULL CHECK (unit IN ('g','ml')),
  stock_qty numeric(10,1) NOT NULL DEFAULT 0 CHECK (stock_qty >= 0), CHECK ((technology='fdm') = (unit='g')), UNIQUE (id, technology));
CREATE TABLE manufacturing.parts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), part_number text NOT NULL UNIQUE, name text NOT NULL,
  scale_code text NOT NULL REFERENCES catalog.scales,
  technology text NOT NULL CHECK (technology IN ('fdm','resin')), material_id uuid NOT NULL,
  layer_height_um smallint NOT NULL CHECK (layer_height_um BETWEEN 10 AND 400),
  plate_minutes int NOT NULL CHECK (plate_minutes > 0), parts_per_plate smallint NOT NULL CHECK (parts_per_plate > 0),
  material_per_part numeric(8,2) NOT NULL CHECK (material_per_part > 0), post_process_minutes int NOT NULL DEFAULT 0,
  UNIQUE (id, scale_code),
  FOREIGN KEY (material_id, technology) REFERENCES manufacturing.materials (id, technology));
CREATE TABLE manufacturing.part_model_files (
  part_id uuid NOT NULL REFERENCES manufacturing.parts ON DELETE CASCADE,
  asset_id uuid NOT NULL, asset_kind text NOT NULL DEFAULT 'model_3d' CHECK (asset_kind = 'model_3d'),
  revision smallint NOT NULL, is_current boolean NOT NULL DEFAULT false,
  PRIMARY KEY (part_id, asset_id), UNIQUE (part_id, revision),
  FOREIGN KEY (asset_id, asset_kind) REFERENCES media.assets (id, kind) ON DELETE RESTRICT);
CREATE UNIQUE INDEX one_current_model ON manufacturing.part_model_files (part_id) WHERE is_current;
CREATE TABLE manufacturing.bom_lines (
  product_scale_id uuid NOT NULL, part_id uuid NOT NULL, scale_code text NOT NULL,
  quantity smallint NOT NULL CHECK (quantity > 0),
  PRIMARY KEY (product_scale_id, part_id),
  FOREIGN KEY (product_scale_id, scale_code) REFERENCES catalog.product_scales (id, scale_code) ON DELETE RESTRICT,
  FOREIGN KEY (part_id, scale_code) REFERENCES manufacturing.parts (id, scale_code) ON DELETE RESTRICT);
CREATE TABLE manufacturing.printers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL UNIQUE, model text NOT NULL,
  technology text NOT NULL CHECK (technology IN ('fdm','resin')),
  state text NOT NULL DEFAULT 'ready' CHECK (state IN ('ready','maintenance','offline','retired')),
  hours_per_day numeric(4,1) NOT NULL DEFAULT 24, loaded_material_id uuid,
  connector text NOT NULL DEFAULT 'manual' CHECK (connector IN ('manual','octoprint','moonraker','prusalink','bambu')),
  FOREIGN KEY (loaded_material_id, technology) REFERENCES manufacturing.materials (id, technology) ON DELETE SET NULL (loaded_material_id));

-- planning (vor print_jobs, wegen proposal_id) ----------------------------
CREATE TABLE planning.calendar_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, starts_on date NOT NULL, ends_on date NOT NULL,
  demand_factor numeric(4,2) NOT NULL CHECK (demand_factor > 0), category_id uuid REFERENCES catalog.categories, CHECK (ends_on >= starts_on));
CREATE TABLE planning.forecast_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), trigger text NOT NULL CHECK (trigger IN ('schedule','event','manual')),
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','succeeded','failed')),
  horizon_days smallint NOT NULL, params jsonb NOT NULL, metrics jsonb, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz);
CREATE TABLE planning.demand_forecasts (
  run_id uuid REFERENCES planning.forecast_runs ON DELETE CASCADE, variant_id uuid REFERENCES catalog.variants ON DELETE RESTRICT,
  demand_class text NOT NULL CHECK (demand_class IN ('smooth','erratic','intermittent','lumpy','new')),
  method text NOT NULL, mean_daily numeric(8,4) NOT NULL, sigma_daily numeric(8,4) NOT NULL, season_factor numeric(4,2) NOT NULL,
  PRIMARY KEY (run_id, variant_id));
CREATE TABLE planning.part_requirements (
  run_id uuid REFERENCES planning.forecast_runs ON DELETE CASCADE, part_id uuid REFERENCES manufacturing.parts ON DELETE RESTRICT,
  on_hand int NOT NULL, in_progress int NOT NULL, allocated int NOT NULL, lead_time_days numeric(5,1) NOT NULL,
  safety_stock numeric(8,1) NOT NULL, reorder_point numeric(8,1) NOT NULL, net_requirement int NOT NULL, stockout_on date,
  PRIMARY KEY (run_id, part_id));
CREATE TABLE planning.print_proposals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL REFERENCES planning.forecast_runs ON DELETE CASCADE,
  rank smallint NOT NULL, printer_id uuid REFERENCES manufacturing.printers ON DELETE SET NULL,
  material_id uuid REFERENCES manufacturing.materials, est_minutes int NOT NULL, score numeric(8,3) NOT NULL,
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','rejected','expired')),
  reasons jsonb NOT NULL, decided_by uuid REFERENCES identity.accounts ON DELETE SET NULL, decided_at timestamptz,
  UNIQUE (run_id, rank), CHECK ((status IN ('proposed','expired')) = (decided_at IS NULL)));
CREATE TABLE planning.print_proposal_lines (
  proposal_id uuid REFERENCES planning.print_proposals ON DELETE CASCADE, part_id uuid REFERENCES manufacturing.parts,
  quantity int NOT NULL CHECK (quantity > 0), covers_until date, PRIMARY KEY (proposal_id, part_id));

CREATE TABLE manufacturing.print_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), printer_id uuid REFERENCES manufacturing.printers ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','printing','post_processing','done','failed','cancelled')),
  source text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','proposal','backorder')),
  proposal_id uuid UNIQUE REFERENCES planning.print_proposals ON DELETE SET NULL,
  planned_minutes int, started_at timestamptz, finished_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (finished_at IS NULL OR finished_at >= started_at),
  CHECK (status <> 'printing' OR (printer_id IS NOT NULL AND started_at IS NOT NULL)));
CREATE UNIQUE INDEX one_running_job ON manufacturing.print_jobs (printer_id) WHERE status = 'printing';
CREATE TABLE manufacturing.print_job_lines (
  job_id uuid REFERENCES manufacturing.print_jobs ON DELETE CASCADE, part_id uuid REFERENCES manufacturing.parts,
  qty_planned int NOT NULL CHECK (qty_planned > 0), qty_good int CHECK (qty_good >= 0), qty_failed int CHECK (qty_failed >= 0),
  PRIMARY KEY (job_id, part_id), CHECK (qty_good IS NULL OR qty_good + coalesce(qty_failed,0) <= qty_planned));

-- sales ------------------------------------------------------------------
CREATE TABLE sales.carts (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL);
CREATE TABLE sales.cart_lines (cart_id uuid REFERENCES sales.carts ON DELETE CASCADE, variant_id uuid REFERENCES catalog.variants ON DELETE RESTRICT,
  quantity smallint NOT NULL CHECK (quantity BETWEEN 1 AND 99), PRIMARY KEY (cart_id, variant_id));
CREATE TABLE sales.orders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), order_number text NOT NULL UNIQUE, public_token uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  status text NOT NULL DEFAULT 'pending_payment' CHECK (status IN ('pending_payment','paid','in_fulfillment','shipped','completed','cancelled','refunded')),
  customer_account_id uuid, customer_kind text NOT NULL DEFAULT 'customer' CHECK (customer_kind = 'customer'),
  email citext NOT NULL, shipping_address jsonb NOT NULL, subtotal_cents int NOT NULL, shipping_cents int NOT NULL DEFAULT 0,
  discount_cents int NOT NULL DEFAULT 0, total_cents int NOT NULL, tax_cents int NOT NULL, placed_at timestamptz NOT NULL DEFAULT now(),
  CHECK (total_cents = subtotal_cents + shipping_cents - discount_cents),
  FOREIGN KEY (customer_account_id, customer_kind) REFERENCES identity.accounts (id, kind) ON DELETE RESTRICT);
CREATE INDEX orders_customer_idx ON sales.orders (customer_account_id) WHERE customer_account_id IS NOT NULL;
CREATE INDEX orders_guest_email_idx ON sales.orders (email) WHERE customer_account_id IS NULL;
CREATE TABLE sales.customer_addresses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL, account_kind text NOT NULL DEFAULT 'customer' CHECK (account_kind = 'customer'),
  label text, recipient text NOT NULL, street text NOT NULL, postal_code text NOT NULL, city text NOT NULL,
  country_code char(2) NOT NULL DEFAULT 'DE' CHECK (country_code ~ '^[A-Z]{2}$'),
  is_default_shipping boolean NOT NULL DEFAULT false, is_default_billing boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (account_id, account_kind) REFERENCES identity.accounts (id, kind) ON DELETE RESTRICT);
CREATE UNIQUE INDEX one_default_shipping ON sales.customer_addresses (account_id) WHERE is_default_shipping;
CREATE UNIQUE INDEX one_default_billing ON sales.customer_addresses (account_id) WHERE is_default_billing;
CREATE TABLE sales.order_lines (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), order_id uuid NOT NULL REFERENCES sales.orders ON DELETE RESTRICT,
  variant_id uuid NOT NULL REFERENCES catalog.variants ON DELETE RESTRICT, sku text NOT NULL, title text NOT NULL,
  unit_price_cents int NOT NULL, quantity int NOT NULL CHECK (quantity > 0), line_total_cents int NOT NULL,
  CHECK (line_total_cents = unit_price_cents * quantity));
CREATE TABLE sales.payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), order_id uuid NOT NULL REFERENCES sales.orders ON DELETE RESTRICT,
  provider text NOT NULL, provider_ref text, status text NOT NULL CHECK (status IN ('pending','authorized','captured','failed','refunded')),
  amount_cents int NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (provider, provider_ref));

-- inventory --------------------------------------------------------------
CREATE TABLE inventory.locations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), parent_id uuid REFERENCES inventory.locations ON DELETE RESTRICT,
  code text NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9]+(-[A-Z0-9]+)*$'),
  kind text NOT NULL CHECK (kind IN ('site','zone','shelf','compartment','box','staging')),
  name text NOT NULL, path ltree NOT NULL UNIQUE, is_active boolean NOT NULL DEFAULT true,
  CHECK ((kind = 'site') = (parent_id IS NULL)));
CREATE INDEX locations_path_gist ON inventory.locations USING gist (path);
CREATE TABLE inventory.part_stock (
  part_id uuid NOT NULL REFERENCES manufacturing.parts ON DELETE RESTRICT,
  location_id uuid NOT NULL REFERENCES inventory.locations ON DELETE RESTRICT,
  quantity int NOT NULL CHECK (quantity >= 0), version int NOT NULL DEFAULT 1, PRIMARY KEY (part_id, location_id));
CREATE TABLE inventory.units (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE CHECK (code ~ '^[0-9A-HJKMNP-TV-Z]{10}$'),
  variant_id uuid NOT NULL REFERENCES catalog.variants ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'labeled' CHECK (status IN ('labeled','in_stock','allocated','picked','shipped','returned','scrapped')),
  location_id uuid REFERENCES inventory.locations ON DELETE RESTRICT,
  order_line_id uuid REFERENCES sales.order_lines ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status NOT IN ('allocated','picked','shipped') OR order_line_id IS NOT NULL),
  CHECK (status NOT IN ('labeled','in_stock') OR order_line_id IS NULL),
  CHECK (status <> 'in_stock' OR location_id IS NOT NULL));
CREATE INDEX units_available ON inventory.units (variant_id, created_at) WHERE status = 'in_stock';
CREATE TABLE inventory.allocations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), order_line_id uuid NOT NULL REFERENCES sales.order_lines ON DELETE RESTRICT,
  strategy text NOT NULL CHECK (strategy IN ('unit','assemble','backorder')), unit_id uuid UNIQUE REFERENCES inventory.units,
  quantity int NOT NULL CHECK (quantity > 0), status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','fulfilled','released')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((strategy = 'unit') = (unit_id IS NOT NULL)), CHECK (strategy <> 'unit' OR quantity = 1));
CREATE TABLE inventory.scan_events (
  id uuid PRIMARY KEY, device_id text NOT NULL, raw text NOT NULL,
  symbology text NOT NULL CHECK (symbology IN ('qr','ean13','ean8','code128','datamatrix','unknown')),
  mode text NOT NULL CHECK (mode IN ('put_away','pick','move','receive','stocktake','return','lookup')),
  outcome text NOT NULL CHECK (outcome IN ('applied','rejected','unknown')), response jsonb NOT NULL,
  actor_id uuid REFERENCES identity.accounts ON DELETE SET NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE inventory.stock_ledger (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, occurred_at timestamptz NOT NULL DEFAULT now(),
  part_id uuid REFERENCES manufacturing.parts, unit_id uuid REFERENCES inventory.units,
  qty_delta int NOT NULL, from_location_id uuid REFERENCES inventory.locations, to_location_id uuid REFERENCES inventory.locations,
  from_status text, to_status text,
  reason text NOT NULL CHECK (reason IN ('receive','put_away','move','assemble','allocate','pick','ship','return','scrap','stocktake','correction')),
  produced_unit_id uuid REFERENCES inventory.units, order_id uuid REFERENCES sales.orders,
  print_job_id uuid REFERENCES manufacturing.print_jobs, scan_event_id uuid REFERENCES inventory.scan_events,
  actor_id uuid REFERENCES identity.accounts ON DELETE SET NULL,
  CHECK (num_nonnulls(part_id, unit_id) = 1),
  CHECK (unit_id IS NULL OR qty_delta IN (-1, 0, 1)),
  CHECK (reason <> 'assemble' OR (part_id IS NOT NULL AND produced_unit_id IS NOT NULL AND qty_delta < 0)));

-- ai / platform ----------------------------------------------------------
CREATE TABLE ai.runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), task text NOT NULL CHECK (task IN ('product_copy','alt_text','planning_brief')),
  prompt_version text NOT NULL, model text NOT NULL, input jsonb NOT NULL, output jsonb,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed')),
  review text NOT NULL DEFAULT 'pending' CHECK (review IN ('pending','applied','partially_applied','discarded')),
  input_tokens int, output_tokens int, cache_read_tokens int, cost_micro_usd bigint, latency_ms int,
  product_id uuid REFERENCES catalog.products ON DELETE SET NULL, requested_by uuid REFERENCES identity.accounts ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz);
ALTER TABLE catalog.product_copy_revisions ADD FOREIGN KEY (ai_run_id) REFERENCES ai.runs ON DELETE RESTRICT;
CREATE TABLE platform.outbox (
  id uuid PRIMARY KEY, event_type text NOT NULL, aggregate_type text NOT NULL, aggregate_id uuid NOT NULL,
  payload jsonb NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz,
  attempts smallint NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now(), last_error text);
CREATE INDEX outbox_pending ON platform.outbox (next_attempt_at) WHERE published_at IS NULL;
-- SSE-Nachholen in Veröffentlichungsreihenfolge und Aufräumen nach 30 Tagen; DSGVO-Schwärzung je Aggregat.
CREATE INDEX outbox_published ON platform.outbox (published_at, id) WHERE published_at IS NOT NULL;
CREATE INDEX outbox_aggregate ON platform.outbox (aggregate_id);
CREATE TABLE platform.idempotency_keys (
  key uuid NOT NULL, scope text NOT NULL, request_hash char(64) NOT NULL, response_status smallint NOT NULL, response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (scope, key));
