import { render, screen, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ActionBarProvider, useActionBarContent, useSetActionBar } from "@/app/action-bar";

function Consumer() {
  const content = useActionBarContent();
  return <div data-testid="slot">{content}</div>;
}

function Producer({ show }: { show: boolean }) {
  useSetActionBar(show ? <button>Re-ingest</button> : null);
  return null;
}

describe("ActionBarProvider", () => {
  it("starts empty and reflects content set by a producer", async () => {
    const { rerender } = render(
      <ActionBarProvider>
        <Consumer />
        <Producer show={false} />
      </ActionBarProvider>,
    );
    expect(screen.getByTestId("slot")).toBeEmptyDOMElement();

    await act(async () => {
      rerender(
        <ActionBarProvider>
          <Consumer />
          <Producer show={true} />
        </ActionBarProvider>,
      );
    });
    expect(screen.getByRole("button", { name: "Re-ingest" })).toBeInTheDocument();
  });

  it("clears content when the producer unmounts", async () => {
    function Wrapper({ mounted }: { mounted: boolean }) {
      return (
        <ActionBarProvider>
          <Consumer />
          {mounted && <Producer show={true} />}
        </ActionBarProvider>
      );
    }
    const { rerender } = render(<Wrapper mounted={true} />);
    expect(screen.getByRole("button", { name: "Re-ingest" })).toBeInTheDocument();

    await act(async () => {
      rerender(<Wrapper mounted={false} />);
    });
    expect(screen.queryByRole("button", { name: "Re-ingest" })).not.toBeInTheDocument();
  });
});
