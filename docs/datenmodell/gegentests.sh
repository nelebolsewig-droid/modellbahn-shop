#!/usr/bin/env bash
# Gegentests für zielmodell.sql: Jede Anweisung verletzt eine Domänenregel und muss
# an genau dem dafür vorgesehenen Constraint scheitern. Die Positivtests müssen gelingen.
#
# Ablauf (PostgreSQL 17 im Container):
#   docker run -d --name mbmodell -e POSTGRES_PASSWORD=modell postgres:17-alpine
#   docker exec -i mbmodell psql -U postgres -c "CREATE DATABASE mb3"
#   docker exec -i mbmodell psql -U postgres -d mb3 -v ON_ERROR_STOP=1 < zielmodell.sql
#   docker exec -i mbmodell psql -U postgres -d mb3 -v ON_ERROR_STOP=1 < beispieldaten.sql
#   ./gegentests.sh
# Ein anderes psql lässt sich über die Umgebungsvariable PSQL setzen.
# Jede Anweisung verletzt eine Domänenregel und muss mit genau dieser Regel scheitern.
P="${PSQL:-docker exec -i mbmodell psql -U postgres -d mb3} -v ON_ERROR_STOP=1 -q"
U=00000000-0000-0000-0000-0000000000
ok=0; nok=0

$P <<'SQL'
INSERT INTO identity.accounts (id,kind,email,display_name,password_hash,role,email_verified_at) VALUES
 ('00000000-0000-0000-0000-0000000000a9','staff','inhaber@modellbahn.local','Inhaber','$argon2id$x','owner',now()),
 ('00000000-0000-0000-0000-0000000000aa','customer','kunde@example.org','Erika','$argon2id$x',NULL,now()),
 ('00000000-0000-0000-0000-0000000000ab','customer','inhaber@modellbahn.local','Inhaber privat','$argon2id$x',NULL,NULL)
ON CONFLICT DO NOTHING;
INSERT INTO sales.customer_addresses (account_id,recipient,street,postal_code,city,is_default_shipping)
SELECT '00000000-0000-0000-0000-0000000000aa','Erika Muster','Bahnhofstr. 1','38707','Altenau',true
WHERE NOT EXISTS (SELECT 1 FROM sales.customer_addresses WHERE account_id='00000000-0000-0000-0000-0000000000aa');
INSERT INTO sales.orders (order_number,customer_account_id,email,shipping_address,subtotal_cents,total_cents,tax_cents) VALUES
 ('MB-2026-00001','00000000-0000-0000-0000-0000000000aa','kunde@example.org','{}',3490,3490,557),
 ('MB-2026-00002',NULL,'gast@example.org','{}',3490,3490,557)
ON CONFLICT DO NOTHING;
SQL
t() { # $1 Beschreibung, $2 erwarteter Constraint, $3 SQL
  err=$($P -c "BEGIN; $3; ROLLBACK;" 2>&1 | grep -m1 ERROR)
  if [[ "$err" == *"$2"* ]]; then ok=$((ok+1)); printf '  ✓ %-44s %s\n' "$1" "$2";
  else nok=$((nok+1)); printf '  ✗ %-44s erwartet %s, bekam: %s\n' "$1" "$2" "${err:-kein Fehler}"; fi; }
MA="INSERT INTO media.assets (id,kind,status,original_key,original_filename,mime_type,size_bytes,sha256) VALUES"
t "N-Dach in H0-Bausatz"                 bom_lines_part_id_scale_code_fkey      "INSERT INTO manufacturing.bom_lines VALUES ('${U}b1','${U}f3','H0',1)"
t "N-Dach mit falsch behaupteter Spur"   bom_lines_product_scale_id_scale_code  "INSERT INTO manufacturing.bom_lines VALUES ('${U}b1','${U}f3','N',1)"
t "Resin-Teil mit FDM-Material"          parts_material_id_technology_fkey      "INSERT INTO manufacturing.materials (id,name,technology,unit) VALUES ('${U}e2','PLA','fdm','g'); INSERT INTO manufacturing.parts (part_number,name,scale_code,technology,material_id,layer_height_um,plate_minutes,parts_per_plate,material_per_part) VALUES ('X','X','H0','resin','${U}e2',25,60,1,1)"
t "STL-Datei als Produktfoto"            product_media_asset_id_asset_kind_fkey "INSERT INTO catalog.product_media (product_id,asset_id,position) VALUES ('${U}a1','${U}32',5)"
t "Foto als Druckdatei"                  part_model_files_asset_id_asset_kind   "INSERT INTO manufacturing.part_model_files (part_id,asset_id,revision) VALUES ('${U}f1','${U}31',1)"
t "Thumbnail für eine STL-Datei"         renditions_asset_id_kind_fkey          "INSERT INTO media.renditions (asset_id,name,format,width_px,height_px,size_bytes,storage_key) VALUES ('${U}32','thumb','webp',1,1,1,'x')"
t "STL-Details an einem Foto"            model_details_asset_id_kind_fkey       "INSERT INTO media.model_details (asset_id,format) VALUES ('${U}31','stl')"
t "zweite aktuelle Druckdatei je Teil"   one_current_model                      "$MA ('${U}33','model_3d','ready','k3','d.stl','model/stl',1,repeat('c',64)); INSERT INTO manufacturing.part_model_files VALUES ('${U}f2','${U}33','model_3d',4,true)"
t "dieselbe Datei zweimal hochgeladen"   assets_dedupe                          "INSERT INTO media.assets (kind,status,original_key,original_filename,mime_type,size_bytes,sha256) VALUES ('image','uploaded','k9','x.jpg','image/jpeg',1,repeat('a',64))"
t "zwei Bilder auf Position 0"           product_media_product_id_position_key  "$MA ('${U}34','image','ready','k4','y.jpg','image/jpeg',1,repeat('d',64)); INSERT INTO catalog.product_media (product_id,asset_id,position) VALUES ('${U}a1','${U}34',0); SET CONSTRAINTS ALL IMMEDIATE"
t "Einheitencode mit I und O"            units_code_check                       "INSERT INTO inventory.units (code,variant_id) VALUES ('7KQ2X9F4OI','${U}d1')"
t "Einheit im Lager ohne Lagerplatz"     units_check2                           "INSERT INTO inventory.units (code,variant_id,status) VALUES ('7KQ2X9F4MK','${U}d1','in_stock')"
t "Einheit versandt ohne Bestellposition" units_check                           "UPDATE inventory.units SET status='shipped' WHERE code='7KQ2X9F4MJ'"
t "negativer Teilebestand"               part_stock_quantity_check              "UPDATE inventory.part_stock SET quantity = -1"
t "Buchung für Teil UND Einheit"         stock_ledger_check                     "INSERT INTO inventory.stock_ledger (part_id,unit_id,qty_delta,reason) VALUES ('${U}f2','00000000-0000-0000-0000-000000000021',1,'move')"
t "Montage ohne erzeugte Einheit"        stock_ledger_check2                    "INSERT INTO inventory.stock_ledger (part_id,qty_delta,reason) VALUES ('${U}f2',-1,'assemble')"
t "Box ohne übergeordneten Platz"        locations_check                        "INSERT INTO inventory.locations (code,kind,name,path) VALUES ('B99','box','Box 99','B99')"
t "Lagerplatz-Code in Kleinbuchstaben"   locations_code_check                   "INSERT INTO inventory.locations (parent_id,code,kind,name,path) VALUES ('00000000-0000-0000-0000-000000000011','r9','shelf','R9','LAGER.R9')"
t "EAN mit Buchstaben"                   variants_gtin_check                    "UPDATE catalog.variants SET gtin='20012340000AB' WHERE sku='STW-ALT-H0-P'"
t "zwei laufende Drucke auf einem Drucker" one_running_job                      "INSERT INTO manufacturing.printers (id,name,model,technology) VALUES ('${U}91','Resin 1','Saturn','resin'); INSERT INTO manufacturing.print_jobs (printer_id,status,started_at) VALUES ('${U}91','printing',now()),('${U}91','printing',now())"
t "mehr gute Teile als geplant"          print_job_lines_check                  "INSERT INTO manufacturing.print_jobs (id) VALUES ('${U}92'); INSERT INTO manufacturing.print_job_lines VALUES ('${U}92','${U}f1',5,6,0)"
t "angenommener Vorschlag ohne Zeitpunkt" print_proposals_check                 "INSERT INTO planning.forecast_runs (id,trigger,horizon_days,params) VALUES ('${U}71','manual',60,'{}'); INSERT INTO planning.print_proposals (run_id,rank,est_minutes,score,status,reasons) VALUES ('${U}71',1,200,1,'accepted','{}')"
t "Bestellsumme passt nicht"             orders_check                           "INSERT INTO sales.orders (order_number,email,shipping_address,subtotal_cents,total_cents,tax_cents) VALUES ('MB-1','a@b.de','{}',1000,999,160)"
t "Variante mit Exemplaren löschen"      units_variant_id_fkey                  "DELETE FROM catalog.variants WHERE sku='STW-ALT-H0-U'"
t "Spurvariante mit Stückliste löschen"  bom_lines_product_scale_id_scale_code  "DELETE FROM catalog.product_scales WHERE id='${U}b1'"
t "KI-Textversion ohne KI-Lauf"          product_copy_revisions_check           "INSERT INTO catalog.product_copy_revisions (product_id,revision,source,fields) VALUES ('${U}a1',1,'ai','{}')"
# Positivfall: Galerie umsortieren muss gelingen (aufgeschobene Eindeutigkeit)
if $P -c "BEGIN; $MA ('${U}35','image','ready','k5','z.jpg','image/jpeg',1,repeat('e',64)); INSERT INTO catalog.product_media (product_id,asset_id,position) VALUES ('${U}a1','${U}35',1); UPDATE catalog.product_media SET position = 1 - position WHERE product_id='${U}a1'; ROLLBACK;" >/dev/null 2>&1
then ok=$((ok+1)); echo "  ✓ Galerie umsortieren (Positionen tauschen) gelingt"; else nok=$((nok+1)); echo "  ✗ Galerie umsortieren scheitert"; fi

# --- Kundenkonten (Modell v3) ---
ACC="INSERT INTO identity.accounts (id,kind,email,display_name,password_hash) VALUES"
ORD="INSERT INTO sales.orders (order_number,customer_account_id,email,shipping_address,subtotal_cents,total_cents,tax_cents) VALUES"
ADR="INSERT INTO sales.customer_addresses (account_id,recipient,street,postal_code,city"
t "Mitarbeiterkonto ohne Rolle"            accounts_check                         "INSERT INTO identity.accounts (kind,email,display_name,password_hash) VALUES ('staff','x@y.de','X','h')"
t "Kundenkonto mit Rolle"                  accounts_check                         "INSERT INTO identity.accounts (kind,email,display_name,password_hash,role) VALUES ('customer','x@y.de','X','h','owner')"
t "Kunden-E-Mail doppelt, andere Schreibung" accounts_kind_email_key              "$ACC (gen_random_uuid(),'customer','KUNDE@Example.org','X','h')"
t "Kundensitzung an Mitarbeiterkonto"      sessions_account_id_kind_fkey          "INSERT INTO identity.sessions (token_hash,account_id,kind,expires_at) VALUES (repeat('a',64),'${U}a9','customer',now()+interval '1 day')"
t "Bestellung an Mitarbeiterkonto"         orders_customer_account_id_customer_ki "$ORD ('MB-X','${U}a9','a@b.de','{}',0,0,0)"
t "Adresse an Mitarbeiterkonto"            customer_addresses_account_id_account_ "$ADR) VALUES ('${U}a9','X','Y','1','Z')"
t "zweite Standard-Lieferadresse"          one_default_shipping                   "$ADR,is_default_shipping) VALUES ('${U}aa','X','Y','1','Z',true)"
t "Konto mit Adresse hart löschen"         customer_addresses_account_id_account_ "$ACC ('${U}ac','customer','z@y.de','Z','h'); $ADR) VALUES ('${U}ac','X','Y','1','Z'); DELETE FROM identity.accounts WHERE id='${U}ac'"
t "Konto mit Bestellung hart löschen"      orders_customer_account_id_customer_ki "$ACC ('${U}ad','customer','w@y.de','W','h'); $ORD ('MB-Y','${U}ad','w@y.de','{}',0,0,0); DELETE FROM identity.accounts WHERE id='${U}ad'"
pos() { if $P -c "BEGIN; $2; ROLLBACK;" >/dev/null 2>&1; then ok=$((ok+1)); printf '  ✓ %-44s gelingt\n' "$1"; else nok=$((nok+1)); printf '  ✗ %-44s scheitert\n' "$1"; fi; }
pos "gleiche E-Mail als Mitarbeiter und Kunde" "$ACC (gen_random_uuid(),'customer','neu@modellbahn.local','N','h'); INSERT INTO identity.accounts (kind,email,display_name,password_hash,role) VALUES ('staff','neu@modellbahn.local','N','h','staff')"
pos "Gastbestellung ohne Konto"            "$ORD ('MB-Z',NULL,'gast2@example.org','{}',0,0,0)"
echo; echo "  $ok bestanden, $nok fehlgeschlagen"
