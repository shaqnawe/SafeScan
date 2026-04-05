import { useState } from "react";
import { scanBarcode } from "./api";
import AddProductPage from "./components/AddProductPage";
import BarcodeScanner from "./components/BarcodeScanner";
import HistoryPage from "./components/HistoryPage";
import HomePage from "./components/HomePage";
import LoadingSpinner from "./components/LoadingSpinner";
import SafetyReportView from "./components/SafetyReport";
import SubmissionsPage from "./components/SubmissionsPage";
import ComparisonPage from "./components/ComparisonPage";
import { useDarkMode } from "./hooks/useDarkMode";
import { useScanHistory } from "./hooks/useScanHistory";
import { useAllergenProfile } from "./hooks/useAllergenProfile";
import AllergenProfilePage from "./components/AllergenProfilePage";
import type { SafetyReport } from "./types";

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
  const isDark = useDarkMode();
  const { history, addEntry, clearHistory } = useScanHistory();
  const { activeIds, activeAllergens, toggleAllergen, clearAll: clearAllergens } = useAllergenProfile();

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
    const bg = isDark ? "#000" : "#f5f5f7";
    const cardBg = isDark ? "#1c1c1e" : "#fff";
    const primaryText = isDark ? "#f2f2f7" : "#1c1c1e";
    const secondaryText = "#8e8e93";
    const dimText = isDark ? "#636366" : "#c7c7cc";
    const borderColor = isDark ? "rgba(255,255,255,0.1)" : "#e5e5ea";
    const scanBtnBg = isDark ? "#2c2c2e" : "#fff";

    return (
      <div
        style={{
          minHeight: "100vh",
          background: bg,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "24px",
          gap: "20px",
        }}
      >
        <div
          style={{
            background: cardBg,
            borderRadius: "24px",
            padding: "40px 32px",
            textAlign: "center",
            maxWidth: "400px",
            width: "100%",
            boxShadow: isDark
              ? "0 2px 20px rgba(0,0,0,0.4)"
              : "0 2px 20px rgba(0,0,0,0.06)",
          }}
        >
          <div style={{ fontSize: "56px", marginBottom: "16px" }}>⚠️</div>
          <h2
            style={{
              fontSize: "22px",
              fontWeight: "700",
              color: primaryText,
              marginBottom: "10px",
            }}
          >
            Analysis Failed
          </h2>
          <p
            style={{
              fontSize: "15px",
              color: secondaryText,
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
                color: dimText,
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
                  background: "#34c759",
                  color: "#fff",
                  fontSize: "16px",
                  fontWeight: "600",
                  cursor: "pointer",
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
                border: `1px solid ${borderColor}`,
                background: scanBtnBg,
                color: primaryText,
                fontSize: "16px",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Scan Different Product
            </button>
          </div>
        </div>

        <p
          style={{
            fontSize: "13px",
            color: secondaryText,
            textAlign: "center",
          }}
        >
          Make sure the backend is running at localhost:8000
        </p>
      </div>
    );
  }

  return null;
}
