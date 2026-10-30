import { z } from "zod";

/*
 * Client-side mirror of the manufacturing input rules (backend/src/modellbahn/modules/
 * manufacturing: domain/model.py and api/schemas.py). The backend stays authoritative
 * and tidies spaces and case; these give immediate feedback in German.
 */

const codePoints = (value: string): number => Array.from(value).length;

const bounded = (max: number, message: string) =>
  z.string().refine((value) => codePoints(value) <= max, { error: message });

/** A whole number typed into a text field; empty means "not given". */
function optionalWhole(min: number, max: number, message: string) {
  return z.string().transform((value, context) => {
    const text = value.trim();
    if (text === "") {
      return null;
    }
    const number = Number(text);
    if (!Number.isInteger(number) || number < min || number > max) {
      context.addIssue({ code: "custom", message });
      return z.NEVER;
    }
    return number;
  });
}

function requiredWhole(min: number, max: number, message: string) {
  return z.string().transform((value, context) => {
    const number = Number(value.trim());
    if (value.trim() === "" || !Number.isInteger(number) || number < min || number > max) {
      context.addIssue({ code: "custom", message });
      return z.NEVER;
    }
    return number;
  });
}

/** Grams or millilitres with up to two decimals, comma or point; empty means unknown. */
const optionalAmount = z.string().transform((value, context) => {
  const text = value.trim().replace(",", ".");
  if (text === "") {
    return null;
  }
  const number = Number(text);
  if (!/^\d+(\.\d{1,2})?$/.test(text) || number <= 0 || number > 100_000) {
    context.addIssue({ code: "custom", message: "Bitte eine Menge wie 3,5 eingeben oder leer lassen." });
    return z.NEVER;
  }
  return number;
});

/** "" stands for "none" in a select. */
const optionalId = z.string().transform((value) => (value === "" ? null : value));

const BUILD_MESSAGE = "Bitte in Millimetern, 1 bis 2000.";

export const printerSchema = z
  .object({
    code: z
      .string()
      .trim()
      .toUpperCase()
      .regex(/^[A-Z0-9]{1,8}$/, "1 bis 8 Buchstaben oder Ziffern, wie auf dem Etikett: D03."),
    name: bounded(60, "Der Name darf höchstens 60 Zeichen lang sein."),
    model: bounded(80, "Das Modell darf höchstens 80 Zeichen lang sein."),
    technology: z.enum(["fdm", "resin"]),
    build_x_mm: optionalWhole(1, 2000, BUILD_MESSAGE),
    build_y_mm: optionalWhole(1, 2000, BUILD_MESSAGE),
    build_z_mm: optionalWhole(1, 2000, BUILD_MESSAGE),
    notes: bounded(500, "Die Notiz darf höchstens 500 Zeichen lang sein."),
  })
  .superRefine((values, context) => {
    const sizes = [values.build_x_mm, values.build_y_mm, values.build_z_mm];
    if (sizes.some((size) => size === null) && sizes.some((size) => size !== null)) {
      context.addIssue({
        code: "custom",
        path: ["build_z_mm"],
        message: "Bitte alle drei Maße des Bauraums angeben oder keines.",
      });
    }
  });

export type PrinterValues = z.input<typeof printerSchema>;

export const EMPTY_PRINTER: PrinterValues = {
  code: "",
  name: "",
  model: "",
  technology: "resin",
  build_x_mm: "",
  build_y_mm: "",
  build_z_mm: "",
  notes: "",
};

export const statusReportSchema = z.object({
  status: z.enum(["in_service", "defective", "in_repair", "retired"]),
  note: bounded(200, "Der Hinweis darf höchstens 200 Zeichen lang sein."),
});

export type StatusReportValues = z.input<typeof statusReportSchema>;

export const materialSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Bitte gib einen Namen ein, z. B. PLA grau.")
    .refine((value) => codePoints(value) <= 60, { error: "Der Name darf höchstens 60 Zeichen lang sein." }),
  technology: z.enum(["fdm", "resin"]),
  notes: bounded(500, "Die Notiz darf höchstens 500 Zeichen lang sein."),
});

export type MaterialValues = z.input<typeof materialSchema>;

export const partSchema = z.object({
  part_number: z
    .string()
    .trim()
    .toUpperCase()
    .max(40, "Die Teilenummer darf höchstens 40 Zeichen lang sein.")
    .regex(/^[A-Z0-9]+(-[A-Z0-9]+)*$/, "Buchstaben, Ziffern und einzelne Bindestriche, z. B. STW-ALT-DACH-H0."),
  name: z
    .string()
    .trim()
    .min(1, "Bitte gib einen Namen ein.")
    .refine((value) => codePoints(value) <= 120, { error: "Der Name darf höchstens 120 Zeichen lang sein." }),
  scale_code: z.string().min(1, "Bitte wähle einen Maßstab."),
  technology: z.enum(["fdm", "resin"]),
  material_id: optionalId,
  layer_height_um: optionalWhole(10, 1000, "Bitte in Mikrometern, 10 bis 1000."),
  plate_minutes: optionalWhole(1, 10_080, "Bitte in Minuten, 1 bis 10080."),
  parts_per_plate: requiredWhole(1, 1000, "Bitte eine Zahl von 1 bis 1000."),
  material_per_part: optionalAmount,
  notes: bounded(500, "Die Notiz darf höchstens 500 Zeichen lang sein."),
  active: z.boolean(),
});

export type PartValues = z.input<typeof partSchema>;

export const EMPTY_PART: PartValues = {
  part_number: "",
  name: "",
  scale_code: "H0",
  technology: "resin",
  material_id: "",
  layer_height_um: "",
  plate_minutes: "",
  parts_per_plate: "1",
  material_per_part: "",
  notes: "",
  active: true,
};

/** Hours and minutes from the slicer, "3:12" or "192"; empty: estimated from the parts. */
export function parseDuration(value: string): number | null | undefined {
  const text = value.trim();
  if (text === "") return null;
  const clock = /^(\d{1,3}):([0-5]\d)$/.exec(text);
  const minutes = clock ? Number(clock[1]) * 60 + Number(clock[2]) : /^\d{1,5}$/.test(text) ? Number(text) : NaN;
  return Number.isInteger(minutes) && minutes >= 1 && minutes <= 10_080 ? minutes : undefined;
}
