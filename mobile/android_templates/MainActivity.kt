package com.example.ai_trade

import android.Manifest
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.content.pm.PackageManager
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    private var termuxPermissionDialogShown = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        startTradingService()

        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 7001)
        } else {
            showTermuxPermissionHelpIfNeeded()
        }
    }

    override fun onResume() {
        super.onResume()
        if (hasTermuxRunCommandPermission()) {
            startTradingService(retry = true)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 7001) {
            showTermuxPermissionHelpIfNeeded()
        }
    }

    private fun hasTermuxRunCommandPermission(): Boolean {
        return Build.VERSION.SDK_INT < 23 ||
            checkSelfPermission("com.termux.permission.RUN_COMMAND") == PackageManager.PERMISSION_GRANTED
    }

    private fun startTradingService(retry: Boolean = false) {
        val serviceIntent = Intent(this, TradingKeepAliveService::class.java)
        if (retry) serviceIntent.action = "com.example.ai_trade.RETRY_BACKEND"
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent)
            } else {
                startService(serviceIntent)
            }
        } catch (_: Exception) {
            // The foreground service reports its state through its persistent notification.
        }
    }

    private fun showTermuxPermissionHelpIfNeeded() {
        if (hasTermuxRunCommandPermission() || termuxPermissionDialogShown || isFinishing) return
        termuxPermissionDialogShown = true

        AlertDialog.Builder(this)
            .setTitle("Enable AI-Trader background engine")
            .setMessage(
                "To start the local trading engine automatically, allow AI-Trader to run commands in Termux. " +
                    "On the next screen open Permissions or Additional permissions, then enable " +
                    "\"Run commands in Termux environment\" (RUN_COMMAND). " +
                    "Termux must also have allow-external-apps=true."
            )
            .setPositiveButton("Open AI-Trader permissions") { _, _ ->
                val appSettings = Intent(
                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:$packageName")
                )
                startActivity(appSettings)
            }
            .setNegativeButton("Later", null)
            .setOnDismissListener { termuxPermissionDialogShown = false }
            .show()
    }
}
