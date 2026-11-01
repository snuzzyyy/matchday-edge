package com.snuzzyyy.matchdayedge;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.content.ClipData;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** Full-screen wrapper around the live Matchday Edge site. Content updates come from the site itself. */
public class MainActivity extends Activity {
    private static final String HOME = "https://snuzzyyy.github.io/matchday-edge/";
    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private static final int PICK_FILE = 42;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#080C18"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " MatchdayEdgeApp/1.3");
        // Lets the site open the phone's own share menu (WhatsApp, Messages, Snapchat...)
        web.addJavascriptInterface(new Object() {
            @JavascriptInterface
            public void share(String text) {
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("text/plain");
                send.putExtra(Intent.EXTRA_TEXT, text);
                runOnUiThread(() -> { try { startActivity(Intent.createChooser(send, "Share")); } catch (Exception ignored) { } });
            }
        }, "MDEApp");
        // Downloads (like a new version of the app) go to the phone's browser
        web.setDownloadListener((url, ua, cd, mime, len) -> { try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); } catch (Exception ignored) { } });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                String url = u.toString();
                // Stay inside the app for the site itself and sign-in links; open bookmakers and everything else in the browser.
                if (url.startsWith(HOME) || "snuzzyyy.github.io".equals(u.getHost()) || (u.getHost() != null && u.getHost().endsWith("supabase.co"))) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
                return true;
            }
        });
        // Lets the site's photo upload open the phone's gallery / file picker
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    Intent pick = params.createIntent();
                    pick.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(Intent.createChooser(pick, "Choose a photo"), PICK_FILE);
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });
        setContentView(web);
        if (state != null) web.restoreState(state);
        else web.loadUrl(HOME);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == PICK_FILE && fileCallback != null) {
            Uri[] picked = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            // some gallery apps hand the photo back as "clip data" instead
            if (picked == null && resultCode == RESULT_OK && data != null && data.getClipData() != null && data.getClipData().getItemCount() > 0) {
                ClipData c = data.getClipData();
                picked = new Uri[] { c.getItemAt(0).getUri() };
            }
            fileCallback.onReceiveValue(picked);
            fileCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); web.saveState(out); }

    @Override
    protected void onResume() { super.onResume(); web.onResume(); }

    @Override
    protected void onPause() { web.onPause(); super.onPause(); }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
