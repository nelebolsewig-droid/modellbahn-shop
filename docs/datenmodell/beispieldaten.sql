-- Beispieldaten für die Gegentests (Stellwerk Altenau in H0 und N, Teile, Lager, Medien).
-- Konten, Adresse sowie Konto- und Gastbestellung legt gegentests.sh selbst an.
INSERT INTO catalog.scales VALUES ('H0','Spur H0',87,16.5),('TT','Spur TT',120,12.0),('N','Spur N',160,9.0);
INSERT INTO catalog.finishes VALUES ('unpainted','Unbemalt',0,0),('primed','Grundiert',15,1),('painted','Fertig bemalt',120,4);
INSERT INTO catalog.epochs VALUES ('III',1949,1970),('IV',1970,1990);
INSERT INTO catalog.categories (id,slug,name) VALUES ('00000000-0000-0000-0000-0000000000c1','gebaeude','Gebäude');
INSERT INTO catalog.products (id,slug,name,primary_category_id,short_description) VALUES
 ('00000000-0000-0000-0000-0000000000a1','stellwerk-altenau','Stellwerk Altenau','00000000-0000-0000-0000-0000000000c1','Mechanisches Stellwerk der Epoche III');
INSERT INTO catalog.product_scales (id,product_id,scale_code) VALUES
 ('00000000-0000-0000-0000-0000000000b1','00000000-0000-0000-0000-0000000000a1','H0'),
 ('00000000-0000-0000-0000-0000000000b2','00000000-0000-0000-0000-0000000000a1','N');
INSERT INTO catalog.variants (id,product_scale_id,finish_code,sku,gtin,price_cents) VALUES
 ('00000000-0000-0000-0000-0000000000d1','00000000-0000-0000-0000-0000000000b1','unpainted','STW-ALT-H0-U','2001234000017',3490),
 ('00000000-0000-0000-0000-0000000000d2','00000000-0000-0000-0000-0000000000b1','painted','STW-ALT-H0-P',NULL,8900);
INSERT INTO manufacturing.materials (id,name,technology,unit) VALUES ('00000000-0000-0000-0000-0000000000e1','Resin 8K Grau','resin','ml');
INSERT INTO manufacturing.parts (id,part_number,name,scale_code,technology,material_id,layer_height_um,plate_minutes,parts_per_plate,material_per_part) VALUES
 ('00000000-0000-0000-0000-0000000000f1','STW-ALT-KOERPER-H0','Gebäudekörper','H0','resin','00000000-0000-0000-0000-0000000000e1',25,220,5,18.5),
 ('00000000-0000-0000-0000-0000000000f2','STW-ALT-DACH-H0','Dach','H0','resin','00000000-0000-0000-0000-0000000000e1',25,140,8,6.0),
 ('00000000-0000-0000-0000-0000000000f3','STW-ALT-DACH-N','Dach','N','resin','00000000-0000-0000-0000-0000000000e1',25,90,20,1.5);
INSERT INTO manufacturing.bom_lines VALUES
 ('00000000-0000-0000-0000-0000000000b1','00000000-0000-0000-0000-0000000000f1','H0',1),
 ('00000000-0000-0000-0000-0000000000b1','00000000-0000-0000-0000-0000000000f2','H0',1);
INSERT INTO inventory.locations (id,parent_id,code,kind,name,path) VALUES
 ('00000000-0000-0000-0000-000000000011',NULL,'LAGER','site','Lager','LAGER'),
 ('00000000-0000-0000-0000-000000000012','00000000-0000-0000-0000-000000000011','R02','shelf','Regal 2','LAGER.R02'),
 ('00000000-0000-0000-0000-000000000013','00000000-0000-0000-0000-000000000012','R02-F04','compartment','Fach 4','LAGER.R02.F04'),
 ('00000000-0000-0000-0000-000000000014','00000000-0000-0000-0000-000000000013','R02-F04-B12','box','Box 12','LAGER.R02.F04.B12');
INSERT INTO inventory.part_stock VALUES ('00000000-0000-0000-0000-0000000000f2','00000000-0000-0000-0000-000000000014',14,1);
INSERT INTO inventory.units (id,code,variant_id,status,location_id) VALUES
 ('00000000-0000-0000-0000-000000000021','7KQ2X9F4MJ','00000000-0000-0000-0000-0000000000d1','in_stock','00000000-0000-0000-0000-000000000014');
INSERT INTO inventory.stock_ledger (part_id,qty_delta,from_location_id,reason,produced_unit_id) VALUES
 ('00000000-0000-0000-0000-0000000000f2',-1,'00000000-0000-0000-0000-000000000014','assemble','00000000-0000-0000-0000-000000000021');
INSERT INTO media.assets (id,kind,status,original_key,original_filename,mime_type,size_bytes,sha256) VALUES
 ('00000000-0000-0000-0000-000000000031','image','ready','incoming/31/original.heic','IMG_0412.HEIC','image/heic',2311000,repeat('a',64)),
 ('00000000-0000-0000-0000-000000000032','model_3d','ready','incoming/32/dach.stl','dach_h0_v3.stl','model/stl',8400000,repeat('b',64));
INSERT INTO media.image_details (asset_id,width_px,height_px) VALUES ('00000000-0000-0000-0000-000000000031',4032,3024);
INSERT INTO media.renditions (asset_id,name,format,width_px,height_px,size_bytes,storage_key) VALUES
 ('00000000-0000-0000-0000-000000000031','thumb','webp',256,256,9100,'public/31/thumb-1a2b3c4d.webp');
INSERT INTO media.model_details (asset_id,format,preview_asset_id) VALUES ('00000000-0000-0000-0000-000000000032','stl','00000000-0000-0000-0000-000000000031');
INSERT INTO catalog.product_media (product_id,asset_id,position,finish_code) VALUES ('00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-000000000031',0,'painted');
INSERT INTO manufacturing.part_model_files (part_id,asset_id,revision,is_current) VALUES ('00000000-0000-0000-0000-0000000000f2','00000000-0000-0000-0000-000000000032',3,true);
