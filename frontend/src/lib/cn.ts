/** Class-name helper re-exported so components import a single symbol. */
import clsx, { type ClassValue } from "clsx";

export function cn(...values: ClassValue[]): string {
  return clsx(values);
}

export type { ClassValue };
export default cn;
