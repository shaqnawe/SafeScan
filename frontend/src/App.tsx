import { useState, useEffect } from "react";
import { Capacitor } from "@capacitor/core";
import { StatusBar, Style } from "@capacitor/status-bar";
import { SplashScreen } from "@capacitor/splash-screen";
import { scanBarcode } from "./api";
import AddProductPage from "./components/AddProductPage";
import BarcodeScanner from "./components/BarcodeScanner";
import HistoryPage from "./components/HistoryPage";
import HomePage from "./components/HomePage";
import LoadingSpinner from "./components/LoadingSpinner";
import SafetyReportView from "./components/SafetyReport";
import SubmissionsPage from "./components/SubmissionsPage";
import ComparisonPage from "./components/ComparisonPage";
import { useTheme } from "./hooks/useDarkMode";
import { useScanHistory } from "./hooks/useScanHistory";
import { useAllergenProfile } from "./hooks/useAllergenProfile";
import AllergenProfilePage from "./components/AllergenProfilePage";
import ThemeToggle from "./components/ThemeToggle";
import { AlertTriangle } from "lucide-react";
import type { SafetyReport } from "./types";
import * as themeImport from "./theme";

type AppState =
  | "home"
  | "scanning"
  | "loading"
  | "result"
  | "error"
  | "history"
  | "add_product"
  | "allergens"
  | "submissions"
  | "comparison";

export default function App() {
  const [state, setState] = useState<AppState>("home");
  const [report, setReport] = useState<SafetyReport | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [scannedBarcode, setScannedBarcode] = useState<string>("");
  const { isDark } = useTheme();
  const { history, addEntry, clearHistory } = useScanHistory();
  const { activeIds, activeAllergens, toggleAllergen, clearAll: clearAllergens } = useAllergenProfile();

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    StatusBar.setStyle({ style: Style.Dark });
    StatusBar.setOverlaysWebView({ overlay: true });
    SplashScreen.hide();
  }, []);

  const handleBarcodeScan = async (barcode: string) => {
    setScannedBarcode(barcode);
    setState("loading");
    setErrorMessage("");

    try {
      const result = await scanBarcode(barcode);
      setReport(result);
      addEntry(result);
      setState("result");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "An unexpected error occurred";
      setErrorMessage(message);
      setState("error");
    }
  };

  const handleScanAgain = () => {
    setReport(null);
    setErrorMessage("");
    setScannedBarcode("");
    setState("home");
  };

  if (state === "home") {
    return (
      <HomePage
        onStartScanning={() => setState("scanning")}
        onViewHistory={() => setState("history")}
        onAllergenProfile={() => setState("allergens")}
        history={history}
        activeAllergenCount={activeIds.length}
        isDark={isDark}
      />
    );
  }

  if (state === "allergens") {
    return (
      <AllergenProfilePage
        activeIds={activeIds}
        onToggle={toggleAllergen}
        onClear={clearAllergens}
        onBack={() => setState("home")}
        isDark={isDark}
      />
    );
  }

  if (state === "history") {
    return (
      <HistoryPage
        history={history}
        onBack={() => setState("scanning")}
        onRescan={handleBarcodeScan}
        onClear={clearHistory}
        isDark={isDark}
      />
    );
  }

  if (state === "comparison") {
    return (
      <ComparisonPage
        onBack={() => setState("scanning")}
        isDark={isDark}
      />
    );
  }

  if (state === "submissions") {
    return (
      <SubmissionsPage
        onBack={() => setState("scanning")}
        onViewReport={(report) => {
          setReport(report);
          setState("result");
        }}
        isDark={isDark}
      />
    );
  }

  if (state === "add_product") {
    return (
      <AddProductPage
        onBack={() => setState("scanning")}
        onAnalyze={handleBarcodeScan}
        onSubmitted={() => setState("submissions")}
        isDark={isDark}
      />
    );
  }

  if (state === "scanning") {
    return (
      <BarcodeScanner
        onScan={handleBarcodeScan}
        history={history}
        onViewHistory={() => setState("history")}
        onAddProduct={() => setState("add_product")}
        onViewSubmissions={() => setState("submissions")}
        onCompare={() => setState("comparison")}
      />
    );
  }

  if (state === "loading") {
    return (
      <LoadingSpinner
        message={`Analyzing ${scannedBarcode}...`}
        isDark={isDark}
      />
    );
  }

  if (state === "result" && report) {
    return (
      <SafetyReportView
        report={report}
        onScanAgain={handleScanAgain}
        isDark={isDark}
        activeAllergens={activeAllergens}
      />
    );
  }

  if (state === "error") {
    const theme = themeImport.getTheme(isDark);
    return (
      <div
        style={{
          minHeight: "100vh",
          background: theme.bg,
          backgroundImage: theme.bgGradient,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "24px",
          gap: "16px",
          fontFamily: themeImport.FONT_STACK,
          position: "relative",
        }}
      >
        <div style={{ position: "fixed", top: 20, right: 20, zIndex: 10 }}>
          <ThemeToggle />
        </div>
        <div
          style={{
            ...themeImport.glassStyle(theme),
            padding: "40px 32px",
            textAlign: "center",
            maxWidth: "400px",
            width: "100%",
          }}
        >
          <div style={{ display: "flex", justifyContent: "center", marginBottom: "16px", color: theme.accent }}>
            <AlertTriangle size={48} strokeWidth={1.75} aria-hidden />
          </div>
          <h2
            style={{
              fontSize: "22px",
              fontWeight: "700",
              color: theme.primary,
              marginBottom: "10px",
              letterSpacing: "-0.02em",
            }}
          >
            Analysis Failed
          </h2>
          <p
            style={{
              fontSize: "15px",
              color: theme.secondary,
              lineHeight: 1.6,
              marginBottom: "8px",
            }}
          >
            {errorMessage ||
              "Something went wrong while analyzing this product."}
          </p>
          {scannedBarcode && (
            <p
              style={{
                fontSize: "13px",
                color: theme.tertiary,
                marginBottom: "24px",
                fontFamily: "monospace",
              }}
            >
              Barcode: {scannedBarcode}
            </p>
          )}
          <div
            style={{ display: "flex", flexDirection: "column", gap: "10px" }}
          >
            {scannedBarcode && (
              <button
                onClick={() => handleBarcodeScan(scannedBarcode)}
                style={{
                  width: "100%",
                  padding: "16px",
                  borderRadius: "14px",
                  border: "none",
                  background: theme.gradeGradient,
                  color: theme.btnText,
                  fontSize: "15px",
                  fontWeight: "700",
                  cursor: "pointer",
                  boxShadow: theme.ctaShadow,
                  fontFamily: themeImport.FONT_STACK,
                }}
              >
                Try Again
              </button>
            )}
            <button
              onClick={handleScanAgain}
              style={{
                width: "100%",
                padding: "16px",
                borderRadius: "14px",
                border: `1px solid ${theme.glassBorder}`,
                background: theme.ingredientBg,
                color: theme.primary,
                fontSize: "15px",
                fontWeight: "600",
                cursor: "pointer",
                fontFamily: themeImport.FONT_STACK,
              }}
            >
              Scan Different Product
            </button>
          </div>
        </div>

        <p
          style={{
            fontSize: "12px",
            color: theme.tertiary,
            textAlign: "center",
            letterSpacing: "0.02em",
          }}
        >
          Make sure the backend is running at localhost:8000
        </p>
      </div>
    );
  }

  return null;
}
