import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiService {
  static const String baseUrl = 'http://127.0.0.1:8000';
  static const Duration timeout = Duration(seconds: 30);

  static Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Duration? requestTimeout,
    bool allowNotFound = false,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    late http.Response response;

    try {
      final duration = requestTimeout ?? timeout;
      if (method == 'GET') {
        response = await http.get(
          uri,
          headers: const {'Accept': 'application/json'},
        ).timeout(duration);
      } else {
        response = await http.post(
          uri,
          headers: const {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
          body: jsonEncode(body ?? {}),
        ).timeout(duration);
      }

      dynamic decoded;
      try {
        decoded = jsonDecode(response.body);
      } on FormatException {
        final detail = response.body.trim();
        if (response.statusCode < 200 || response.statusCode >= 300) {
          throw Exception(
            'HTTP ${response.statusCode}${detail.isEmpty ? '' : ': ${detail.substring(0, detail.length > 180 ? 180 : detail.length)}'}',
          );
        }
        throw Exception('Server returned an invalid JSON response');
      }

      if (decoded is! Map<String, dynamic>) {
        throw Exception('Invalid server response format');
      }

      if (allowNotFound &&
          response.statusCode == 404 &&
          decoded['request_status'] == 'NOT_FOUND') {
        return decoded;
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception(
          decoded['reason'] ??
          decoded['error'] ??
          'HTTP ${response.statusCode}',
        );
      }
      return decoded;
    } on Exception catch (e) {
      throw Exception('API request failed ($path): $e');
    } catch (e) {
      throw Exception('API request failed ($path): $e');
    }
  }

  static Future<Map<String, dynamic>> marketSymbols(String market) =>
      _request(
        'GET',
        '/market/symbols?market=${Uri.encodeQueryComponent(market)}',
      );

  static Future<Map<String, dynamic>> marketCandles({
    required String market,
    required String symbol,
    String interval = '5m',
    int limit = 200,
    bool live = false,
    int? startTime,
    int? endTime,
  }) =>
      _request(
        'GET',
        '/market/candles?market=${Uri.encodeQueryComponent(market)}'
        '&symbol=${Uri.encodeQueryComponent(symbol)}'
        '&interval=${Uri.encodeQueryComponent(interval)}'
        '&limit=$limit'
        '${live ? '&live=1' : ''}'
        '${startTime == null ? '' : '&startTime=$startTime'}'
        '${endTime == null ? '' : '&endTime=$endTime'}',
      );

  static Future<bool> health() async {
    final result = await _request(
      'GET', '/health', requestTimeout: const Duration(seconds: 5));
    return result['ok'] == true && result['api_version'] == '2026.11.10.4';
  }

  static Future<Map<String, dynamic>> status() =>
      _request('GET', '/status', requestTimeout: const Duration(seconds: 8));

  static Future<Map<String, dynamic>> telegramStatus() =>
      _request('GET', '/notifications/status');

  static Future<Map<String, dynamic>> configureTelegram({
    required String botToken,
    required String chatId,
  }) =>
      _request('POST', '/notifications/configure', body: {
        'bot_token': botToken,
        'chat_id': chatId,
      });

  static Future<Map<String, dynamic>> testTelegram() =>
      _request('POST', '/notifications/test');

  static Future<Map<String, dynamic>> setMode(String mode) =>
      _request('POST', '/mode', body: {'mode': mode});

  static Future<Map<String, dynamic>> analyze(String symbol) =>
      _request('POST', '/analyze', body: {'symbol': symbol});

  static Future<Map<String, dynamic>> submitChartSignal({
    required String domain,
    required String symbol,
    required String timeframe,
    required double entryPrice,
    required double takeProfit,
    required double stopLoss,
  }) =>
      _request('POST', '/agent/submit', body: {
        'domain': domain,
        'symbol': symbol,
        'timeframe': timeframe,
        'entry_price': entryPrice,
        'take_profit': takeProfit,
        'stop_loss': stopLoss,
      }, requestTimeout: const Duration(seconds: 25));

  static Future<Map<String, dynamic>> agentSubmissionStatus(String requestId) =>
      _request(
        'GET',
        '/agent/submission?id=${Uri.encodeQueryComponent(requestId)}',
        allowNotFound: true,
      );

  static Future<Map<String, dynamic>> tradeChart({
    required String tradeId,
  }) =>
      _request(
        'GET',
        '/journal/chart?trade_id=${Uri.encodeQueryComponent(tradeId)}',
      );

  static Future<Map<String, dynamic>> scanFutures() =>
      _request('POST', '/scan/futures');

  static Future<Map<String, dynamic>> demoPositions() =>
      _request('GET', '/demo/positions');

  static Future<Map<String, dynamic>> closeDemoTrade({
    required String positionId,
  }) =>
      _request('POST', '/demo/close', body: {
        'position_id': positionId,
      });

  static Future<Map<String, dynamic>> depositDemoBalance(double amount) =>
      _request('POST', '/demo/deposit', body: {'amount': amount});

  static Future<Map<String, dynamic>> stopAgent(String domain) =>
      _request('POST', '/agents/$domain/stop');

  static Future<Map<String, dynamic>> resumeAgent(String domain) =>
      _request('POST', '/agents/$domain/resume');

  static Future<Map<String, dynamic>> emergencyStop() =>
      _request('POST', '/emergency-stop');

  static Future<Map<String, dynamic>> resumeAll() =>
      _request('POST', '/resume-all');

  static Future<Map<String, dynamic>> performance() =>
      _request('GET', '/performance');

  static Future<Map<String, dynamic>> learning() =>
      _request('GET', '/learning');

  static Future<Map<String, dynamic>> journal({
    int limit = 30,
    bool closedOnly = false,
  }) =>
      _request(
        'GET',
        closedOnly ? '/journal?closed=1' : '/journal?limit=$limit',
      );

  static Future<Map<String, dynamic>> autopilot() =>
      _request('GET', '/autopilot');

  static Future<Map<String, dynamic>> autopilotUpdate(
    Map<String, dynamic> changes,
  ) =>
      _request('POST', '/autopilot', body: changes);

  static Future<Map<String, dynamic>> autopilotRun() =>
      _request('POST', '/autopilot/run');

  static Future<Map<String, dynamic>> enableSetup(String setup) =>
      _request('POST', '/learning/enable', body: {'setup': setup});
}
