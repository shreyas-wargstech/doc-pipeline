import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Composer } from "@/components/aether/Composer";

describe("Composer", () => {
  it("fires onSlash when input becomes '/'", () => {
    const onSlash = vi.fn();
    render(<Composer value="" onChange={() => {}} onSubmit={() => {}} onSlash={onSlash} chips={[]} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "/" } });
    expect(onSlash).toHaveBeenCalled();
  });
  it("submits on Enter", () => {
    const onSubmit = vi.fn();
    render(<Composer value="hi" onChange={() => {}} onSubmit={onSubmit} onSlash={() => {}} chips={[]} />);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSubmit).toHaveBeenCalled();
  });
});
