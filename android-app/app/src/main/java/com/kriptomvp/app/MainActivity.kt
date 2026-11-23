package com.kriptomvp.app

import android.annotation.SuppressLint
import android.content.SharedPreferences
import android.os.Bundle
import android.text.InputType
import android.view.Menu
import android.view.MenuItem
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.ProgressBar
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * Jednostavan WebView omotač oko kripto-trading dashboarda (vidi crypto-trading/README.md).
 * Adresa servera se unosi ručno u Postavkama i sprema u SharedPreferences - IP adresa računala
 * na lokalnoj mreži obično se mijenja (DHCP), pa je ne želimo hardkodirati u kodu.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var progressBar: ProgressBar
    private lateinit var prefs: SharedPreferences

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = getSharedPreferences("kripto_mvp_prefs", MODE_PRIVATE)

        setSupportActionBar(findViewById<Toolbar>(R.id.toolbar).also { it.title = getString(R.string.app_name) })

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        progressBar = findViewById(R.id.progressBar)
        findViewById<android.widget.Button>(R.id.emptyStateButton).setOnClickListener { showSettingsDialog() }

        setupWebView()
        swipeRefresh.setOnRefreshListener { webView.reload() }

        loadServerUrlOrPrompt()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.databaseEnabled = true
        webView.settings.loadWithOverviewMode = true
        webView.settings.useWideViewPort = true
        webView.settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                swipeRefresh.isRefreshing = false
                progressBar.visibility = android.view.View.GONE
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    swipeRefresh.isRefreshing = false
                    progressBar.visibility = android.view.View.GONE
                }
            }
        }

        webView.webChromeClient = object : android.webkit.WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                super.onProgressChanged(view, newProgress)
                if (newProgress in 1..99) {
                    progressBar.visibility = android.view.View.VISIBLE
                    progressBar.progress = newProgress
                } else {
                    progressBar.visibility = android.view.View.GONE
                }
            }
        }
    }

    private fun loadServerUrlOrPrompt() {
        val saved = prefs.getString(PREF_SERVER_URL, null)
        if (saved.isNullOrBlank()) {
            showEmptyState(true)
            showSettingsDialog()
        } else {
            showEmptyState(false)
            webView.loadUrl(normalizeUrl(saved))
        }
    }

    private fun showEmptyState(show: Boolean) {
        findViewById<android.view.View>(R.id.emptyState).visibility = if (show) android.view.View.VISIBLE else android.view.View.GONE
        webView.visibility = if (show) android.view.View.GONE else android.view.View.VISIBLE
    }

    private fun normalizeUrl(input: String): String {
        val trimmed = input.trim()
        return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed else "http://$trimmed"
    }

    private fun showSettingsDialog() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            hint = getString(R.string.settings_hint)
            setText(prefs.getString(PREF_SERVER_URL, ""))
        }

        AlertDialog.Builder(this)
            .setTitle(R.string.settings_title)
            .setView(input)
            .setPositiveButton(R.string.settings_save) { _, _ ->
                val value = input.text.toString().trim()
                if (value.isNotEmpty()) {
                    prefs.edit().putString(PREF_SERVER_URL, value).apply()
                    showEmptyState(false)
                    webView.loadUrl(normalizeUrl(value))
                }
            }
            .setNegativeButton(R.string.settings_cancel, null)
            .show()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_settings -> {
                showSettingsDialog()
                true
            }
            R.id.action_refresh -> {
                webView.reload()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    companion object {
        private const val PREF_SERVER_URL = "server_url"
    }
}
