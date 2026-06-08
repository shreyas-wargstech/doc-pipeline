import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Filters } from "@/components/Filters";

describe("Filters", () => {
  afterEach(() => vi.useRealTimers());

  it("emits the selected status filter", async () => {
    const onChange = vi.fn();
    render(<Filters value={{}} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText(/status/i), "processed");
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ status: "processed" }));
  });

  it("emits debounced search text", async () => {
    const onChange = vi.fn();
    render(<Filters value={{}} onChange={onChange} />);
    await userEvent.type(screen.getByPlaceholderText(/reg.*filename/i), "349");
    // Not yet fired (debounce is 300ms, real timers — just check it hasn't fired synchronously)
    // Wait for debounce to fire
    await vi.waitFor(
      () => expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ search: "349" })),
      { timeout: 1000 }
    );
  });
});
