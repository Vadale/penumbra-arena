// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotificationSettings, readEnabledKinds } from "../NotificationSettings";

interface MockNotification {
  permission: NotificationPermission;
  requestPermission: () => Promise<NotificationPermission>;
}

function installNotificationMock(initial: NotificationPermission = "default"): MockNotification {
  const mock: MockNotification = {
    permission: initial,
    requestPermission: vi.fn(async (): Promise<NotificationPermission> => {
      mock.permission = "granted";
      return "granted";
    }),
  };
  Object.defineProperty(window, "Notification", {
    value: mock,
    configurable: true,
    writable: true,
  });
  return mock;
}

function clearNotificationMock() {
  // Remove the property entirely so subsequent tests start clean.
  // We use a write of undefined + delete because some browsers/jsdom
  // builds disallow delete on Window.
  try {
    Object.defineProperty(window, "Notification", {
      value: undefined,
      configurable: true,
      writable: true,
    });
  } catch {
    // ignore
  }
}

describe("NotificationSettings", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    clearNotificationMock();
    vi.restoreAllMocks();
  });

  it("renders one checkbox per supported event kind", () => {
    installNotificationMock("default");
    render(<NotificationSettings />);
    expect(screen.getByLabelText(/notify on cpi\.shock/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/notify on garch\.spike/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/notify on agent\.blocked/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/notify on chain\.block\.finalised/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/notify on validator\.slashed/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/notify on ml\.policy\.updated/i)).toBeInTheDocument();
  });

  it("toggling a checkbox persists the enabled state to localStorage", async () => {
    installNotificationMock("default");
    render(<NotificationSettings />);
    const checkbox = screen.getByLabelText(/notify on cpi\.shock/i) as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    fireEvent.click(checkbox);
    await waitFor(() => {
      expect(window.localStorage.getItem("penumbra.notifications.cpi.shock")).toBe("1");
    });
    expect(readEnabledKinds().has("cpi.shock")).toBe(true);
    // Toggling off removes the key.
    fireEvent.click(checkbox);
    await waitFor(() => {
      expect(window.localStorage.getItem("penumbra.notifications.cpi.shock")).toBeNull();
    });
    expect(readEnabledKinds().has("cpi.shock")).toBe(false);
  });

  it("'enable browser notifications' calls Notification.requestPermission and updates the badge", async () => {
    const mock = installNotificationMock("default");
    render(<NotificationSettings />);
    const button = screen.getByRole("button", { name: /enable browser notifications/i });
    fireEvent.click(button);
    await waitFor(() => {
      expect(mock.requestPermission).toHaveBeenCalledOnce();
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^granted$/i })).toBeInTheDocument();
    });
  });

  it("shows the 'denied' badge and a disabled button when permission is denied", () => {
    installNotificationMock("denied");
    render(<NotificationSettings />);
    expect(screen.getByLabelText(/notification permission denied/i)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: /blocked in browser/i });
    expect(button).toBeDisabled();
  });

  it("renders an unsupported placeholder when Notification API is missing", () => {
    clearNotificationMock();
    render(<NotificationSettings />);
    expect(screen.getByLabelText(/notification permission unsupported/i)).toBeInTheDocument();
  });
});
