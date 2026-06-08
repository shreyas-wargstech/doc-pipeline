import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Filters } from "@/components/Filters";

describe("Filters", () => {
  it("emits the selected status filter", async () => {
    const onChange = vi.fn();
    render(<Filters value={{}} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText(/status/i), "processed");
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ status: "processed" }));
  });

  it("emits search text", async () => {
    const onChange = vi.fn();
    render(<Filters value={{}} onChange={onChange} />);
    await userEvent.type(screen.getByPlaceholderText(/reg.*filename/i), "3");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ search: "3" }));
  });
});
