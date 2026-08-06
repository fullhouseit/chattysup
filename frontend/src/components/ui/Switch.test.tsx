/**
 * Geometry regression for {@link Switch}.
 *
 * The knob is absolutely positioned, so it needs an explicit inset: without one
 * the browser lays it out at a static position of its own choosing and the
 * translate that moves it to the "on" side starts from the wrong origin. That
 * is how the knob ended up 14px outside the track — on every toggle in the app.
 *
 * These assertions read the class list rather than a rendered layout so they
 * run without a browser, but they pin the exact invariant that broke:
 * inset + on-translate + knob width must equal the track width minus the inset.
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Switch } from "./Switch";

/** Tailwind spacing unit -> px (0.25rem = 4px, 1rem = 16px). */
const px = (unit: number) => unit * 4;

const INSET = px(0.5); // left-0.5 / top-0.5
const SIZES = {
  md: { track: px(9), height: px(5), knob: px(4), onTranslate: px(4) },
  sm: { track: px(7), height: px(4), knob: px(3), onTranslate: px(3) },
};

function knobClasses(checked: boolean, size?: "sm") {
  const { container } = render(
    <Switch checked={checked} onChange={() => {}} size={size} />,
  );
  const knob = container.querySelector("[role=switch] span");
  return knob?.className ?? "";
}

describe("Switch knob geometry", () => {
  it.each(["md", "sm"] as const)("%s: the knob never leaves the track", (size) => {
    const spec = SIZES[size];
    // left edge when on + knob width must stay inside the track.
    const onLeft = INSET + spec.onTranslate;
    expect(onLeft + spec.knob).toBeLessThanOrEqual(spec.track);
    // …and the gap should match the one on the other side.
    expect(spec.track - (onLeft + spec.knob)).toBe(INSET);
    // vertical, too.
    expect(INSET + spec.knob + INSET).toBe(spec.height);
  });

  it("pins the knob with an explicit inset in both states", () => {
    for (const checked of [true, false]) {
      expect(knobClasses(checked)).toContain("left-0.5");
      expect(knobClasses(checked)).toContain("top-0.5");
    }
  });

  it("uses the translate the geometry above assumes", () => {
    expect(knobClasses(false)).toContain("translate-x-0");
    expect(knobClasses(true)).toContain("translate-x-4");
    expect(knobClasses(true, "sm")).toContain("translate-x-3");
  });
});
