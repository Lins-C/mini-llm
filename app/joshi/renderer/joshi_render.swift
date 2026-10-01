// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
// JOSHI-Renderer: lädt eine HTML-Datei in WebKit (dieselbe Engine wie Safari),
// führt ein Prüfskript aus und erzeugt auf Wunsch Bild und PDF der ganzen Seite.
//
// Aufruf (alle Pfade absolut):
//   joshi-render --html seite.html [--prelude vorrede.js] [--probe pruefung.js]
//                [--breite 1280] [--hoehe 900] [--png bild.png] [--pdf seite.pdf]
//                [--seiten-pdf druck.pdf] [--skala 2] [--timeout 30] [--warten 0.6]
//
// Ausgabe: genau ein JSON-Objekt auf stdout. Der Renderer entscheidet nichts —
// er misst nur. Was als Fehler zählt, legt der Python-Validator fest.
import Cocoa
import WebKit

struct Optionen {
    var html = ""
    var prelude: String?
    var probe: String?
    var breite: CGFloat = 1280
    var hoehe: CGFloat = 900
    var png: String?
    var pdf: String?
    var seitenPdf: String?
    var skala: CGFloat = 2
    var timeout: Double = 30
    var warten: Double = 0.6
    var maxHoehe: CGFloat = 20000
}

func liesOptionen() -> Optionen {
    var o = Optionen()
    var args = Array(CommandLine.arguments.dropFirst())
    while !args.isEmpty {
        let schluessel = args.removeFirst()
        guard !args.isEmpty else { break }
        let wert = args.removeFirst()
        switch schluessel {
        case "--html": o.html = wert
        case "--prelude": o.prelude = try? String(contentsOfFile: wert, encoding: .utf8)
        case "--probe": o.probe = try? String(contentsOfFile: wert, encoding: .utf8)
        case "--breite": o.breite = CGFloat(Double(wert) ?? 1280)
        case "--hoehe": o.hoehe = CGFloat(Double(wert) ?? 900)
        case "--png": o.png = wert
        case "--pdf": o.pdf = wert
        case "--seiten-pdf": o.seitenPdf = wert
        case "--skala": o.skala = CGFloat(Double(wert) ?? 2)
        case "--timeout": o.timeout = Double(wert) ?? 30
        case "--warten": o.warten = Double(wert) ?? 0.6
        case "--max-hoehe": o.maxHoehe = CGFloat(Double(wert) ?? 20000)
        default: break
        }
    }
    return o
}

final class Renderer: NSObject, WKNavigationDelegate, WKUIDelegate {
    let o: Optionen
    var fenster: NSWindow!
    var web: WKWebView!
    var ergebnis: [String: Any] = [:]
    var dialoge: [String] = []
    var blockierteNavigation: [String] = []
    var geladen = false
    var beendet = false

    init(_ o: Optionen) { self.o = o }

    func start() {
        guard let html = try? String(contentsOfFile: o.html, encoding: .utf8) else {
            return fertig(fehler: "HTML-Datei nicht lesbar")
        }
        let konfiguration = WKWebViewConfiguration()
        konfiguration.websiteDataStore = .nonPersistent()
        // Das Fenster ist nie sichtbar. WebKit drosselt Timer verborgener Seiten
        // nach rund einer Sekunde auf 1 s — gemessen: zehnmal 80 ms, danach je
        // 1.000 ms; eine Bedienprobe mit 30 Klicks dauerte so 22 s.
        if #available(macOS 14.0, *) {
            konfiguration.preferences.inactiveSchedulingPolicy = .none
        }
        let praeferenzen = konfiguration.preferences
        for (schalter, name) in [
            ("_setHiddenPageDOMTimerThrottlingEnabled:", "hiddenPageDOMTimerThrottlingEnabled"),
            ("_setPageVisibilityBasedProcessSuppressionEnabled:", "pageVisibilityBasedProcessSuppressionEnabled"),
        ] where praeferenzen.responds(to: Selector(schalter)) {
            praeferenzen.setValue(false, forKey: name)
        }
        let inhalt = WKUserContentController()
        if let vorrede = o.prelude {
            inhalt.addUserScript(WKUserScript(
                source: vorrede, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        }
        konfiguration.userContentController = inhalt
        let rahmen = NSRect(x: 0, y: 0, width: o.breite, height: o.hoehe)
        web = WKWebView(frame: rahmen, configuration: konfiguration)
        web.navigationDelegate = self
        web.uiDelegate = self
        fenster = NSWindow(contentRect: rahmen, styleMask: [.borderless],
                           backing: .buffered, defer: false)
        fenster.isReleasedWhenClosed = false
        fenster.contentView = web
        fenster.setFrameOrigin(NSPoint(x: -20000, y: -20000))
        // Eine eigene (nie erreichte) Herkunft: Mit baseURL nil meldet WebKit
        // Fehler aus Inline-Skripten nur als „Script error.“ ohne Text.
        web.loadHTMLString(html, baseURL: URL(string: "https://produkt.joshi.invalid/"))
        DispatchQueue.main.asyncAfter(deadline: .now() + o.timeout) { [weak self] in
            self?.fertig(fehler: "Zeitüberschreitung nach \(Int(self?.o.timeout ?? 0)) s — die Seite hängt vermutlich in einer Endlosschleife")
        }
    }

    // --- Navigation: Nur das Laden der Seite selbst ist erlaubt.
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = navigationAction.request.url
        // Während des initialen Ladevorgangs ist ausschließlich die von
        // loadHTMLString gesetzte, künstliche Hauptframe-Herkunft erlaubt.
        // Ein Redirect oder meta-refresh darf die Prüfseite nicht vor
        // didFinish aus WebKit heraus navigieren.
        if !geladen,
           navigationAction.targetFrame?.isMainFrame == true,
           ((url?.scheme == "https" &&
             url?.host == "produkt.joshi.invalid" &&
             (url?.path.isEmpty == true || url?.path == "/") &&
             url?.query == nil && url?.fragment == nil) ||
            url?.absoluteString == "about:blank") {
            return decisionHandler(.allow)
        }
        // Interne Anker dürfen die laufende Single-Page-Anwendung weiterhin
        // bedienen, ändern aber weder Herkunft noch Dokument.
        if geladen,
           navigationAction.targetFrame?.isMainFrame == true,
           url?.scheme == "https",
           url?.host == "produkt.joshi.invalid",
           (url?.path.isEmpty == true || url?.path == "/"),
           url?.query == nil,
           url?.fragment != nil {
            return decisionHandler(.allow)
        }
        // Nach dem Laden darf die Seite sich nicht mehr selbst ersetzen: Ein
        // Download-Knopf (blob:) oder ein Formular zerstörte sonst mitten in der
        // Bedienprobe die Seite — gemessen am 19.09. mit „Als CSV exportieren“.
        let urlText = url?.absoluteString ?? ""
        let hauptrahmen = navigationAction.targetFrame?.isMainFrame ?? true
        if !hauptrahmen && (urlText.hasPrefix("about:") || urlText.hasPrefix("data:") || urlText.hasPrefix("blob:")) {
            return decisionHandler(.allow)
        }
        blockierteNavigation.append(String(urlText.prefix(200)))
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if geladen { return }
        geladen = true
        DispatchQueue.main.asyncAfter(deadline: .now() + o.warten) { [weak self] in
            self?.pruefen()
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        if !geladen { fertig(fehler: "Laden fehlgeschlagen: \(error.localizedDescription)") }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: Error) {
        if !geladen { fertig(fehler: "Laden fehlgeschlagen: \(error.localizedDescription)") }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        fertig(fehler: "Der Browserprozess der Seite ist abgestürzt (Speicher oder Endlosschleife)")
    }

    // --- Dialoge: Im JOSHI-Sandkasten verpufft alert(); hier wird es gezählt.
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        dialoge.append(String(message.prefix(200)))
        completionHandler()
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        dialoge.append(String(message.prefix(200)))
        completionHandler(true)
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                 defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (String?) -> Void) {
        dialoge.append(String(prompt.prefix(200)))
        completionHandler(defaultText ?? "")
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        blockierteNavigation.append("window.open " + (navigationAction.request.url?.absoluteString ?? ""))
        return nil
    }

    // --- Prüfung
    func pruefen() {
        guard let probe = o.probe else { return exportieren() }
        web.callAsyncJavaScript(probe, arguments: [:], in: nil, in: .page) { [weak self] antwort in
            guard let self = self else { return }
            switch antwort {
            case .success(let wert):
                if let text = wert as? String,
                   let daten = text.data(using: .utf8),
                   let objekt = try? JSONSerialization.jsonObject(with: daten) {
                    self.ergebnis["probe"] = objekt
                } else {
                    self.ergebnis["probe"] = NSNull()
                }
            case .failure(let fehler):
                self.ergebnis["probeFehler"] = "\(fehler)"
            }
            self.exportieren()
        }
    }

    func seitenhoehe(_ weiter: @escaping (CGFloat) -> Void) {
        let js = "Math.ceil(Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0))"
        web.evaluateJavaScript(js) { wert, _ in
            weiter(CGFloat((wert as? NSNumber)?.doubleValue ?? Double(self.o.hoehe)))
        }
    }

    func exportieren() {
        if o.png == nil && o.pdf == nil && o.seitenPdf == nil { return fertig(fehler: nil) }
        // Für das Gesamtbild wächst das Fenster auf die volle Seitenhöhe. Seiten
        // mit 100vh wachsen dabei mit; zwei Durchgänge fangen das ab.
        seitenhoehe { erste in
            let ziel = min(self.o.maxHoehe, max(self.o.hoehe, erste))
            self.groesse(ziel)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                self.seitenhoehe { zweite in
                    let hoehe = min(self.o.maxHoehe, max(ziel, zweite))
                    if hoehe > ziel { self.groesse(hoehe) }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                        self.ergebnis["seitenhoehe"] = Double(hoehe)
                        self.ergebnis["abgeschnitten"] = erste > self.o.maxHoehe
                        self.pdfUndBild(hoehe)
                    }
                }
            }
        }
    }

    func groesse(_ hoehe: CGFloat) {
        let rahmen = NSRect(x: -20000, y: -20000, width: o.breite, height: hoehe)
        fenster.setFrame(rahmen, display: false)
        web.frame = NSRect(x: 0, y: 0, width: o.breite, height: hoehe)
    }

    func pdfUndBild(_ hoehe: CGFloat) {
        let konfiguration = WKPDFConfiguration()
        konfiguration.rect = CGRect(x: 0, y: 0, width: o.breite, height: hoehe)
        web.createPDF(configuration: konfiguration) { [weak self] antwort in
            guard let self = self else { return }
            switch antwort {
            case .success(let daten):
                if let ziel = self.o.pdf {
                    try? daten.write(to: URL(fileURLWithPath: ziel))
                    self.ergebnis["pdf"] = ziel
                }
                if let ziel = self.o.png {
                    if self.rastern(daten, nach: ziel) { self.ergebnis["png"] = ziel }
                    else { self.ergebnis["pngFehler"] = "Rastern fehlgeschlagen" }
                }
            case .failure(let fehler):
                self.ergebnis["pdfFehler"] = "\(fehler)"
            }
            if let ziel = self.o.seitenPdf { self.drucken(nach: ziel) } else { self.fertig(fehler: nil) }
        }
    }

    // Das Bild entsteht aus dem Vektor-PDF — so ist die Auflösung unabhängig vom
    // Bildschirm des Mac mini (der kann auch ganz fehlen).
    func rastern(_ daten: Data, nach ziel: String) -> Bool {
        guard let anbieter = CGDataProvider(data: daten as CFData),
              let dokument = CGPDFDocument(anbieter),
              let seite = dokument.page(at: 1) else { return false }
        let kasten = seite.getBoxRect(.mediaBox)
        let breite = Int(kasten.width * o.skala), hoehe = Int(kasten.height * o.skala)
        guard breite > 0, hoehe > 0,
              let farbraum = CGColorSpace(name: CGColorSpace.sRGB),
              let kontext = CGContext(data: nil, width: breite, height: hoehe, bitsPerComponent: 8,
                                      bytesPerRow: 0, space: farbraum,
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        else { return false }
        kontext.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        kontext.fill(CGRect(x: 0, y: 0, width: breite, height: hoehe))
        kontext.scaleBy(x: o.skala, y: o.skala)
        kontext.drawPDFPage(seite)
        guard let bild = kontext.makeImage() else { return false }
        let rep = NSBitmapImageRep(cgImage: bild)
        guard let png = rep.representation(using: .png, properties: [:]) else { return false }
        do { try png.write(to: URL(fileURLWithPath: ziel)) } catch { return false }
        ergebnis["bild"] = ["breite": breite, "hoehe": hoehe]
        return true
    }

    // Druckfassung: A4-Seiten mit echtem Text, wie „Drucken → Als PDF sichern“.
    func drucken(nach ziel: String) {
        groesse(o.hoehe)
        let info = NSPrintInfo()
        info.paperSize = NSSize(width: 595.28, height: 841.89)
        info.topMargin = 28; info.bottomMargin = 28; info.leftMargin = 28; info.rightMargin = 28
        info.horizontalPagination = .fit
        info.verticalPagination = .automatic
        info.jobDisposition = .save
        info.dictionary()[NSPrintInfo.AttributeKey.jobSavingURL] = URL(fileURLWithPath: ziel)
        let operation = web.printOperation(with: info)
        operation.showsPrintPanel = false
        operation.showsProgressPanel = false
        operation.view?.frame = NSRect(x: 0, y: 0, width: o.breite, height: o.hoehe)
        operation.runModal(for: fenster, delegate: self,
                           didRun: #selector(druckFertig(_:erfolg:kontext:)), contextInfo: nil)
    }

    @objc func druckFertig(_ operation: NSPrintOperation, erfolg: Bool, kontext: UnsafeMutableRawPointer?) {
        if erfolg, let ziel = o.seitenPdf { ergebnis["seitenPdf"] = ziel }
        else { ergebnis["seitenPdfFehler"] = "Druck fehlgeschlagen" }
        fertig(fehler: nil)
    }

    func fertig(fehler: String?) {
        if beendet { return }
        beendet = true
        ergebnis["ok"] = fehler == nil
        ergebnis["geladen"] = geladen
        if let fehler = fehler { ergebnis["fehler"] = fehler }
        ergebnis["dialoge"] = dialoge
        ergebnis["navigation"] = blockierteNavigation
        if let daten = try? JSONSerialization.data(withJSONObject: ergebnis, options: []),
           let text = String(data: daten, encoding: .utf8) {
            FileHandle.standardOutput.write((text + "\n").data(using: .utf8)!)
        } else {
            FileHandle.standardOutput.write("{\"ok\":false,\"fehler\":\"Ergebnis nicht serialisierbar\"}\n".data(using: .utf8)!)
        }
        exit(fehler == nil ? 0 : 2)
    }
}

let optionen = liesOptionen()
let anwendung = NSApplication.shared
anwendung.setActivationPolicy(.prohibited)
let renderer = Renderer(optionen)
DispatchQueue.main.async { renderer.start() }
anwendung.run()
