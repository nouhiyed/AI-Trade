import 'dart:math' as math;
import 'package:flutter/material.dart';

void main() => runApp(const AITradeApp());

const bg = Color(0xFF070B16);
const panel = Color(0xFF101A2B);
const panel2 = Color(0xFF142239);
const cyan = Color(0xFF00E5C3);
const blue = Color(0xFF39A8FF);
const violet = Color(0xFF9B72FF);
const muted = Color(0xFF8997B0);
const green = Color(0xFF21D6A1);
const red = Color(0xFFFF647C);

class AITradeApp extends StatelessWidget {
  const AITradeApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: bg,
      fontFamily: 'sans-serif',
      colorScheme: const ColorScheme.dark(primary: cyan, surface: panel),
      useMaterial3: true,
    ),
    home: const Directionality(textDirection: TextDirection.rtl, child: TradeShell()),
  );
}

class TradeShell extends StatefulWidget {
  const TradeShell({super.key});
  @override
  State<TradeShell> createState() => _TradeShellState();
}

class _TradeShellState extends State<TradeShell> with TickerProviderStateMixin {
  int page = 0;
  bool demo = true;
  bool running = true;
  late final AnimationController pulse = AnimationController(vsync: this, duration: const Duration(seconds: 7))..repeat();
  final List<String> pages = ['الرئيسية', 'الوكلاء', 'الأسواق', 'المحفظة', 'الإعدادات'];

  @override
  void dispose() { pulse.dispose(); super.dispose(); }

  void notify(String s) => ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(s), behavior: SnackBarBehavior.floating, backgroundColor: panel2),
  );

  @override
  Widget build(BuildContext context) {
    final bodies = [
      _home(),
      AgentsPage(running: running, onToggle: () => setState(() => running = !running)),
      const MarketsPage(),
      const WalletPage(),
      const SettingsPage(),
    ];
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(children: [
          _topBar(),
          Expanded(child: AnimatedSwitcher(duration: const Duration(milliseconds: 280), child: KeyedSubtree(key: ValueKey(page), child: bodies[page]))),
          _bottomBar(),
        ]),
      ),
    );
  }

  Widget _topBar() => Padding(
    padding: const EdgeInsets.fromLTRB(20, 12, 20, 14),
    child: Row(children: [
      Container(width: 44, height: 44, decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(15),
        gradient: const LinearGradient(colors: [cyan, blue, violet], begin: Alignment.topLeft, end: Alignment.bottomRight),
        boxShadow: [BoxShadow(color: cyan.withOpacity(.18), blurRadius: 22)],
      ), child: const Icon(Icons.auto_awesome, color: bg, size: 25)),
      const SizedBox(width: 12),
      const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('AI TRADE', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, letterSpacing: 2.1)),
        Text('مركز القيادة الذكي', style: TextStyle(color: muted, fontSize: 11)),
      ]),
      const Spacer(),
      _roundIcon(Icons.notifications_none_rounded, () => notify('لا توجد تنبيهات جديدة')),
      const SizedBox(width: 8),
    ]),
  );

  Widget _roundIcon(IconData icon, VoidCallback tap) => InkWell(
    onTap: tap, borderRadius: BorderRadius.circular(14),
    child: Container(width: 40, height: 40, decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(14), border: Border.all(color: Colors.white.withOpacity(.06))), child: Icon(icon, color: cyan, size: 21)),
  );

  Widget _home() => ListView(
    key: const PageStorageKey('home'),
    padding: const EdgeInsets.fromLTRB(16, 0, 16, 22),
    children: [
      _hero(),
      const SizedBox(height: 14),
      _portfolioCard(),
      const SizedBox(height: 22),
      _sectionTitle('نبض السوق', 'LIVE PREVIEW', Icons.candlestick_chart_rounded),
      const SizedBox(height: 10),
      const MarketChartCard(compact: true),
      const SizedBox(height: 18),
      _sectionTitle('مركز التنفيذ', 'PAPER TRADING', Icons.bolt_rounded),
      const SizedBox(height: 9),
      _quickTradePanel(),
      const SizedBox(height: 18),
      _sectionTitle('فريق الوكلاء', '3 AGENTS', Icons.hub_rounded),
      const SizedBox(height: 10),
      _agentRow('Futures Agent', 'العقود الآجلة', 'يراقب 126 زوجاً', cyan, Icons.show_chart_rounded, true),
      _agentRow('Spot Agent', 'التداول الفوري', 'يراقب 84 زوجاً', blue, Icons.currency_bitcoin_rounded, true),
      _agentRow('Alpha Agent', 'اصطياد الفرص الجديدة', 'تحليل فرص Alpha', violet, Icons.bolt_rounded, false),
      const SizedBox(height: 16),
      _sectionTitle('آخر النشاطات', 'ACTIVITY', Icons.bolt_rounded),
      const SizedBox(height: 8),
      _activity('اكتمل فحص السوق', 'Futures Agent · منذ لحظات', cyan),
      _activity('لا توجد صفقة مفتوحة', 'Risk Engine · آمن', green),
    ],
  );

  Widget _hero() => Container(
    height: 250,
    clipBehavior: Clip.antiAlias,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(26),
      border: Border.all(color: cyan.withOpacity(.24)),
      gradient: const LinearGradient(colors: [Color(0xFF102D3B), Color(0xFF15152D), Color(0xFF0C1324)], begin: Alignment.topLeft, end: Alignment.bottomRight),
    ),
    child: Stack(children: [
      Positioned.fill(child: CustomPaint(painter: GridPainter())),
      Positioned(left: -30, top: -30, child: AnimatedBuilder(animation: pulse, builder: (_, __) => SizedBox(width: 255, height: 255, child: CustomPaint(painter: OrbPainter(pulse.value))))),
      Positioned(left: 6, bottom: 10, child: SizedBox(width: 190, height: 90, child: CustomPaint(painter: MiniAgentLinks(pulse.value)))),
      Positioned(right: 20, top: 20, child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Row(mainAxisSize: MainAxisSize.min, children: const [Icon(Icons.bolt, color: cyan, size: 17), SizedBox(width: 5), Text('منظومة التداول الذكية', style: TextStyle(color: cyan, fontWeight: FontWeight.w700, fontSize: 12))]),
        const SizedBox(height: 18),
        const Text('ثلاثة وكلاء.', style: TextStyle(fontSize: 27, fontWeight: FontWeight.w900)),
        const Text('عقل تداول واحد', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: cyan)),
        const SizedBox(height: 8),
        const SizedBox(width: 205, child: Text('تحليل مستقل، إدارة مخاطر مشتركة، وقرارات منسّقة.', textAlign: TextAlign.right, style: TextStyle(color: Color(0xFFAAB8CC), height: 1.5, fontSize: 12))),
        const SizedBox(height: 12),
        Container(padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 8), decoration: BoxDecoration(color: cyan.withOpacity(.10), border: Border.all(color: cyan.withOpacity(.35)), borderRadius: BorderRadius.circular(30)), child: const Text('النظام في وضع الاستعداد', style: TextStyle(color: cyan, fontSize: 11, fontWeight: FontWeight.bold))),
      ])),
    ]),
  );

  Widget _portfolioCard() => Container(
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(25), border: Border.all(color: Colors.white.withOpacity(.07))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [const Text('إجمالي المحفظة', style: TextStyle(color: muted, fontSize: 12)), const Spacer(), _tag('DEMO', blue)]),
      const SizedBox(height: 10),
      const Text('\$1,000.00', style: TextStyle(fontSize: 37, fontWeight: FontWeight.w900, letterSpacing: -.8)),
      const Text('رصيد تجريبي · غير متصل بـ Binance', style: TextStyle(color: muted, fontSize: 11)),
      const SizedBox(height: 20),
      Row(children: const [
        Expanded(child: _Metric('الربح', '\$0.00', cyan)),
        Expanded(child: _Metric('المتاح', '\$1,000', Colors.white)),
        Expanded(child: _Metric('الصفقات', '0', Colors.white)),
      ]),
      const SizedBox(height: 18),
      Row(children: [
        Expanded(child: OutlinedButton(onPressed: () {}, style: OutlinedButton.styleFrom(foregroundColor: muted, side: const BorderSide(color: Color(0xFF34445D)), padding: const EdgeInsets.symmetric(vertical: 14), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15))), child: const Text('تداول حقيقي مقفل'))),
        const SizedBox(width: 10),
        Expanded(child: FilledButton(onPressed: () {}, style: FilledButton.styleFrom(backgroundColor: cyan.withOpacity(.13), foregroundColor: cyan, side: const BorderSide(color: cyan), padding: const EdgeInsets.symmetric(vertical: 14), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15))), child: const Text('تداول تجريبي'))),
      ]),
    ]),
  );

  Widget _quickTradePanel() => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: panel,
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: violet.withOpacity(.25)),
    ),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Row(children: [
        Icon(Icons.bolt, color: violet, size: 18),
        SizedBox(width: 7),
        Text('صفقة تجريبية سريعة', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
        Spacer(),
        Text('NO REAL ORDERS', style: TextStyle(color: muted, fontSize: 8, letterSpacing: 1)),
      ]),
      const SizedBox(height: 11),
      Row(children: [
        Expanded(child: FilledButton.icon(
          onPressed: () => _showPaperTrade('شراء / LONG'),
          icon: const Icon(Icons.trending_up_rounded),
          label: const Text('شراء'),
          style: FilledButton.styleFrom(backgroundColor: green.withOpacity(.16), foregroundColor: green, padding: const EdgeInsets.symmetric(vertical: 14), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13))),
        )),
        const SizedBox(width: 9),
        Expanded(child: FilledButton.icon(
          onPressed: () => _showPaperTrade('بيع / SHORT'),
          icon: const Icon(Icons.trending_down_rounded),
          label: const Text('بيع'),
          style: FilledButton.styleFrom(backgroundColor: red.withOpacity(.15), foregroundColor: red, padding: const EdgeInsets.symmetric(vertical: 14), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13))),
        )),
      ]),
      const SizedBox(height: 8),
      const Text('الأزرار تعرض تأكيداً تجريبياً فقط؛ لا يتم إرسال أوامر إلى Binance.', style: TextStyle(color: muted, fontSize: 9)),
    ]),
  );

  void _showPaperTrade(String side) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: panel2,
        title: const Text('محاكاة أمر تداول'),
        content: Text('تم اختيار $side على BTC/USDT. هذه نسخة واجهة تجريبية ولا يوجد تنفيذ أو خصم من الرصيد.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('إغلاق')),
          FilledButton(onPressed: () {
            Navigator.pop(dialogContext);
            notify('تمت معاينة أمر $side — لم يُرسل أي أمر حقيقي');
          }, child: const Text('تأكيد المعاينة')),
        ],
      ),
    );
  }

  Widget _sectionTitle(String title, String sub, IconData icon) => Row(children: [
    Icon(icon, color: cyan, size: 19), const SizedBox(width: 7),
    Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
    const Spacer(), Text(sub, style: const TextStyle(color: muted, fontSize: 9, letterSpacing: 1.2)),
  ]);

  Widget _agentRow(String name, String ar, String detail, Color color, IconData icon, bool active) => Container(
    margin: const EdgeInsets.only(bottom: 8),
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(18), border: Border.all(color: color.withOpacity(.16))),
    child: Row(children: [
      Container(width: 42, height: 42, decoration: BoxDecoration(color: color.withOpacity(.12), borderRadius: BorderRadius.circular(14)), child: Icon(icon, color: color)),
      const SizedBox(width: 11),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)), Text('$ar · $detail', style: const TextStyle(color: muted, fontSize: 10))])),
      Container(width: 7, height: 7, decoration: BoxDecoration(color: active ? green : muted, shape: BoxShape.circle, boxShadow: active ? [BoxShadow(color: green.withOpacity(.7), blurRadius: 8)] : [])),
      const SizedBox(width: 6), Text(active ? 'نشط' : 'انتظار', style: TextStyle(color: active ? green : muted, fontSize: 10)),
    ]),
  );

  Widget _activity(String title, String detail, Color color) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Row(children: [Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)), const SizedBox(width: 10), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)), Text(detail, style: const TextStyle(color: muted, fontSize: 10))])), const Icon(Icons.chevron_left, color: muted, size: 18)]),
  );

  Widget _tag(String text, Color color) => Container(padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6), decoration: BoxDecoration(color: color.withOpacity(.10), borderRadius: BorderRadius.circular(30), border: Border.all(color: color.withOpacity(.35))), child: Text(text, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.bold)));

  Widget _bottomBar() => Container(
    padding: const EdgeInsets.fromLTRB(8, 8, 8, 20),
    decoration: BoxDecoration(color: const Color(0xFF0B1220), border: Border(top: BorderSide(color: Colors.white.withOpacity(.06)))),
    child: Row(children: List.generate(5, (i) {
      final icons = [Icons.grid_view_rounded, Icons.hub_rounded, Icons.candlestick_chart_rounded, Icons.account_balance_wallet_rounded, Icons.settings_rounded];
      return Expanded(child: InkWell(
        onTap: () => setState(() => page = i),
        borderRadius: BorderRadius.circular(17),
        child: AnimatedContainer(duration: const Duration(milliseconds: 220), padding: const EdgeInsets.symmetric(vertical: 8), decoration: BoxDecoration(color: page == i ? cyan.withOpacity(.12) : Colors.transparent, borderRadius: BorderRadius.circular(17)),
          child: Column(mainAxisSize: MainAxisSize.min, children: [Icon(icons[i], color: page == i ? cyan : muted, size: 22), const SizedBox(height: 4), Text(pages[i], style: TextStyle(color: page == i ? cyan : muted, fontSize: 9, fontWeight: page == i ? FontWeight.bold : FontWeight.normal))]),
        ),
      ));
    })),
  );
}

class _Metric extends StatelessWidget {
  final String title, value; final Color color;
  const _Metric(this.title, this.value, this.color);
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(color: muted, fontSize: 10)), const SizedBox(height: 5), Text(value, style: TextStyle(color: color, fontSize: 17, fontWeight: FontWeight.w800))]);
}

class AgentsPage extends StatefulWidget {
  final bool running; final VoidCallback onToggle;
  const AgentsPage({super.key, required this.running, required this.onToggle});
  @override
  State<AgentsPage> createState() => _AgentsPageState();
}
class _AgentsPageState extends State<AgentsPage> with SingleTickerProviderStateMixin {
  late final AnimationController c = AnimationController(vsync: this, duration: const Duration(seconds: 12))..repeat();
  int selected = 0;
  @override
  void dispose() { c.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 20), children: [
    const _PageHeading('شبكة الوكلاء العصبية', 'NEURAL COMMAND NETWORK'),
    const SizedBox(height: 12),
    Container(height: 300, decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(25), border: Border.all(color: cyan.withOpacity(.18))), child: Stack(children: [
      Positioned.fill(child: AnimatedBuilder(animation: c, builder: (_, __) => CustomPaint(painter: NetworkPainter(c.value, selected)))),
      const Positioned(top: 15, right: 16, child: Text('LIVE TOPOLOGY', style: TextStyle(color: muted, fontSize: 9, letterSpacing: 1.5))),
      Positioned(bottom: 14, left: 14, right: 14, child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: const [ _Legend(cyan, 'FUTURES'), _Legend(blue, 'SPOT'), _Legend(violet, 'ALPHA') ])),
    ])),
    const SizedBox(height: 15),
    Row(children: [const Expanded(child: Text('حالة المنظومة', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold))), Text(widget.running ? 'النظام يعمل تجريبياً' : 'متوقف', style: TextStyle(color: widget.running ? green : red, fontSize: 11))]),
    const SizedBox(height: 10),
    _agentCard(0, 'Futures Agent', 'تحليل العقود الآجلة', cyan, Icons.show_chart, '126 زوجاً · 4 أطر زمنية', 'يفحص الزخم، الاتجاه، السيولة ومناطق الدخول.'),
    _agentCard(1, 'Spot Agent', 'إدارة فرص السوق الفوري', blue, Icons.currency_bitcoin, '84 زوجاً · مراقبة دورية', 'يبحث عن فرص الشراء الفوري ويوازن المخاطر.'),
    _agentCard(2, 'Alpha Agent', 'اكتشاف الأصول المبكرة', violet, Icons.bolt, 'مصادر Alpha · فحص أمان', 'يفحص السيولة والعقود ومخاطر التوكن قبل التوصية.'),
    const SizedBox(height: 8),
    FilledButton.icon(onPressed: widget.onToggle, icon: Icon(widget.running ? Icons.pause_rounded : Icons.play_arrow_rounded), label: Text(widget.running ? 'إيقاف الوكلاء التجريبي' : 'تشغيل الوكلاء التجريبي'), style: FilledButton.styleFrom(backgroundColor: widget.running ? red.withOpacity(.15) : cyan.withOpacity(.15), foregroundColor: widget.running ? red : cyan, padding: const EdgeInsets.all(15))),
    const Padding(padding: EdgeInsets.only(top: 9), child: Text('هذه لوحة تفاعلية تجريبية؛ لا يوجد اتصال حي بمحركات التداول في هذه النسخة.', textAlign: TextAlign.center, style: TextStyle(color: muted, fontSize: 10))),
  ]);
  Widget _agentCard(int i, String name, String ar, Color color, IconData icon, String status, String desc) => InkWell(
    onTap: () => setState(() => selected = i),
    borderRadius: BorderRadius.circular(18),
    child: AnimatedContainer(duration: const Duration(milliseconds: 180), margin: const EdgeInsets.only(bottom: 9), padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: selected == i ? color.withOpacity(.10) : panel, borderRadius: BorderRadius.circular(18), border: Border.all(color: selected == i ? color.withOpacity(.65) : Colors.white.withOpacity(.06), width: selected == i ? 1.4 : 1)),
      child: Row(children: [Container(width: 43, height: 43, decoration: BoxDecoration(color: color.withOpacity(.13), borderRadius: BorderRadius.circular(14)), child: Icon(icon, color: color)), const SizedBox(width: 12), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)), Text(ar, style: const TextStyle(color: muted, fontSize: 10)), if (selected == i) Padding(padding: const EdgeInsets.only(top: 7), child: Text(desc, style: const TextStyle(color: Color(0xFFB8C6D9), fontSize: 10, height: 1.4)))])), Column(crossAxisAlignment: CrossAxisAlignment.end, children: [Text(status, style: TextStyle(color: color, fontSize: 9)), const SizedBox(height: 7), Icon(selected == i ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down, color: muted)])]),
    ),
  );
}

class MarketsPage extends StatelessWidget {
  const MarketsPage({super.key});
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 20), children: [
    const _PageHeading('مركز الأسواق', 'MARKET INTELLIGENCE'),
    const SizedBox(height: 12),
    const MarketChartCard(compact: false),
    const SizedBox(height: 14),
    const Text('قائمة المراقبة', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
    const SizedBox(height: 9),
    _coin('₿', 'BTC / USDT', 'Bitcoin', '\$67,420.00', '+2.41%', cyan),
    _coin('Ξ', 'ETH / USDT', 'Ethereum', '\$3,520.80', '+1.28%', blue),
    _coin('◎', 'SOL / USDT', 'Solana', '\$184.32', '-0.74%', violet),
    const SizedBox(height: 8),
    const Text('الأسعار والرسوم في هذه الشاشة توضيحية وليست أسعار سوق مباشرة.', style: TextStyle(color: muted, fontSize: 10), textAlign: TextAlign.center),
  ]);
  Widget _coin(String symbol, String pair, String name, String price, String change, Color color) => Container(margin: const EdgeInsets.only(bottom: 8), padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(17)), child: Row(children: [Container(width: 38, height: 38, alignment: Alignment.center, decoration: BoxDecoration(color: color.withOpacity(.13), borderRadius: BorderRadius.circular(13)), child: Text(symbol, style: TextStyle(color: color, fontSize: 20, fontWeight: FontWeight.bold))), const SizedBox(width: 10), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(pair, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)), Text(name, style: const TextStyle(color: muted, fontSize: 10))])), Column(crossAxisAlignment: CrossAxisAlignment.end, children: [Text(price, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)), Text(change, style: TextStyle(color: change.startsWith('+') ? green : red, fontSize: 10))])]));
}

class MarketChartCard extends StatefulWidget {
  final bool compact;
  const MarketChartCard({super.key, required this.compact});
  @override
  State<MarketChartCard> createState() => _MarketChartCardState();
}
class _MarketChartCardState extends State<MarketChartCard> {
  String tf = '1H'; double zoom = 1; double drag = 0;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(15),
    decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(23), border: Border.all(color: Colors.white.withOpacity(.07))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('BTC / USDT', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)), Text('Bitcoin · PREVIEW', style: TextStyle(color: muted, fontSize: 9, letterSpacing: 1))]), const Spacer(), const Text('\$67,420.00', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900)),]),
      const SizedBox(height: 3),
      const Row(children: [Text('+2.41%', style: TextStyle(color: green, fontWeight: FontWeight.bold, fontSize: 11)), SizedBox(width: 6), Text('24h illustrative change', style: TextStyle(color: muted, fontSize: 9))]),
      const SizedBox(height: 12),
      Row(
        children: ['15m', '1H', '4H', '1D'].map((s) {
          return Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 3),
              child: InkWell(
                onTap: () => setState(() => tf = s),
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 7),
                  decoration: BoxDecoration(
                    color: tf == s ? cyan.withOpacity(.14) : panel2,
                    borderRadius: BorderRadius.circular(9),
                    border: Border.all(color: tf == s ? cyan.withOpacity(.5) : Colors.transparent),
                  ),
                  child: Text(s, textAlign: TextAlign.center,
                    style: TextStyle(color: tf == s ? cyan : muted, fontSize: 10, fontWeight: FontWeight.bold)),
                ),
              ),
            ),
          );
        }).toList(),
      ),
      const SizedBox(height: 8),
      SizedBox(height: widget.compact ? 175 : 255, child: GestureDetector(
        onScaleUpdate: (d) => setState(() { zoom = (zoom * d.scale).clamp(.75, 2.4); drag += d.focalPointDelta.dx * .15; }),
        child: CustomPaint(painter: CandlePainter(zoom, drag), child: const SizedBox.expand()),
      )),
      Row(children: const [ _Legend(green, 'BULLISH'), _Legend(red, 'BEARISH'), Spacer(), Text('اسحب للتنقل · كبّر بإصبعين', style: TextStyle(color: muted, fontSize: 9)) ]),
      if (!widget.compact) const Padding(padding: EdgeInsets.only(top: 12), child: Row(children: [Expanded(child: _Indicator('RSI (14)', '58.4', cyan)), Expanded(child: _Indicator('MACD', '+124.8', violet)), Expanded(child: _Indicator('VOLUME', 'NORMAL', blue))])),
    ]),
  );
}

class _Indicator extends StatelessWidget {
  final String a,b; final Color c;
  const _Indicator(this.a,this.b,this.c);
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(a, style: const TextStyle(color: muted, fontSize: 9)), const SizedBox(height: 4), Text(b, style: TextStyle(color: c, fontWeight: FontWeight.bold, fontSize: 12))]);
}

class WalletPage extends StatelessWidget {
  const WalletPage({super.key});
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 20), children: [
    const _PageHeading('المحفظة والتحليلات', 'PORTFOLIO ANALYTICS'),
    const SizedBox(height: 14),
    Container(padding: const EdgeInsets.all(20), decoration: BoxDecoration(borderRadius: BorderRadius.circular(24), gradient: const LinearGradient(colors: [Color(0xFF123C4A), Color(0xFF182342), Color(0xFF251B42)])), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Text('إجمالي قيمة المحفظة · DEMO', style: TextStyle(color: Color(0xFFB5C8D8), fontSize: 11)), const SizedBox(height: 8), const Text('\$1,000.00', style: TextStyle(fontSize: 35, fontWeight: FontWeight.w900)), const SizedBox(height: 15), SizedBox(height: 90, child: CustomPaint(painter: EquityPainter(), child: const SizedBox.expand())), const Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text('نمو تجريبي', style: TextStyle(color: muted, fontSize: 10)), Text('لا توجد صفقات مسجلة', style: TextStyle(color: cyan, fontSize: 10))]) ])),
    const SizedBox(height: 16),
    const Text('توزيع رأس المال', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
    const SizedBox(height: 10),
    Container(padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(20)), child: Row(children: [SizedBox(width: 112, height: 112, child: CustomPaint(painter: DonutPainter())), const SizedBox(width: 18), const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [_Legend(cyan, 'متاح 100%'), SizedBox(height: 12), _Legend(blue, 'Spot 0%'), SizedBox(height: 12), _Legend(violet, 'Futures 0%')]))])),
    const SizedBox(height: 16),
    const Text('سجل الصفقات', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
    const SizedBox(height: 8),
    Container(padding: const EdgeInsets.all(25), decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(18)), child: const Column(children: [Icon(Icons.receipt_long_rounded, color: muted, size: 30), SizedBox(height: 8), Text('لا توجد صفقات حتى الآن', style: TextStyle(color: muted, fontSize: 12)), Text('ستظهر هنا نتائج التداول التجريبي', style: TextStyle(color: muted, fontSize: 10))])),
  ]);
}

class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 20), children: [
    const _PageHeading('الإعدادات والتحكم', 'SYSTEM CONFIGURATION'),
    const SizedBox(height: 14),
    _setting(Icons.science_outlined, 'وضع التداول التجريبي', 'مفعّل دائماً في هذه النسخة لحماية أموالك', const _StatusPill('DEMO ACTIVE', cyan)),
    _setting(Icons.notifications_active_outlined, 'مركز التنبيهات', 'عرض تنبيهات النظام من أيقونة الجرس بالأعلى', const Icon(Icons.notifications_active, color: cyan)),
    _setting(Icons.shield_outlined, 'محرك إدارة المخاطر', 'حدود الخسارة وحماية رأس المال', const Icon(Icons.verified_user, color: green)),
    _setting(Icons.key_rounded, 'ربط Binance API', 'غير متصل · لا توجد مفاتيح محفوظة', const Icon(Icons.lock_outline, color: muted)),
    const SizedBox(height: 16),
    Container(padding: const EdgeInsets.all(17), decoration: BoxDecoration(color: red.withOpacity(.07), borderRadius: BorderRadius.circular(19), border: Border.all(color: red.withOpacity(.25))), child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Row(children: [Icon(Icons.lock_outline, color: red), SizedBox(width: 8), Text('التداول الحقيقي غير مفعّل', style: TextStyle(color: red, fontWeight: FontWeight.bold))]), SizedBox(height: 7), Text('لن يتم إرسال أوامر حقيقية قبل ربط API آمن وتفعيل الصلاحيات بموافقتك الصريحة.', style: TextStyle(color: muted, fontSize: 11, height: 1.5))])),
    const SizedBox(height: 18),
    const Center(child: Text('AI TRADE · BUILD 0.2.0 · DEMO UI', style: TextStyle(color: muted, fontSize: 9, letterSpacing: 1.2))),
  ]);
  Widget _setting(IconData icon, String title, String sub, Widget trailing) => Container(margin: const EdgeInsets.only(bottom: 9), padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: panel, borderRadius: BorderRadius.circular(17)), child: Row(children: [Icon(icon, color: cyan, size: 21), const SizedBox(width: 12), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)), Text(sub, style: const TextStyle(color: muted, fontSize: 10))])), trailing]));
}
class _StatusPill extends StatelessWidget {
  final String label; final Color color;
  const _StatusPill(this.label,this.color);
  @override
  Widget build(BuildContext context) => Container(padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6), decoration: BoxDecoration(color: color.withOpacity(.10), border: Border.all(color: color.withOpacity(.4)), borderRadius: BorderRadius.circular(20)), child: Text(label, style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.bold)));
}

class _PageHeading extends StatelessWidget {
  final String title, sub;
  const _PageHeading(this.title,this.sub);
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900)), const SizedBox(height: 3), Text(sub, style: const TextStyle(color: muted, fontSize: 9, letterSpacing: 1.7))]);
}
class _Legend extends StatelessWidget {
  final Color color; final String text;
  const _Legend(this.color,this.text);
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [Container(width: 7,height: 7,decoration: BoxDecoration(color: color,shape: BoxShape.circle,boxShadow: [BoxShadow(color: color.withOpacity(.5),blurRadius: 6)])), const SizedBox(width: 5), Text(text,style: const TextStyle(color: muted,fontSize: 9))]);
}

class MiniAgentLinks extends CustomPainter {
  final double t;
  MiniAgentLinks(this.t);
  @override
  void paint(Canvas canvas, Size size) {
    final pts = [Offset(size.width*.18,size.height*.28), Offset(size.width*.50,size.height*.08), Offset(size.width*.82,size.height*.28)];
    final cols = [cyan,blue,violet];
    final center = Offset(size.width*.5,size.height*.70);
    for (var i=0;i<3;i++) {
      canvas.drawLine(center,pts[i],Paint()..color=cols[i].withOpacity(.55)..strokeWidth=1.4);
      canvas.drawCircle(pts[i],8,Paint()..color=cols[i].withOpacity(.16));
      canvas.drawCircle(pts[i],3.2,Paint()..color=cols[i]);
      final f=(t+i*.29)%1;
      canvas.drawCircle(Offset.lerp(center,pts[i],f)!,2.4,Paint()..color=cols[i]);
    }
    canvas.drawCircle(center,10,Paint()..color=cyan.withOpacity(.25));
    canvas.drawCircle(center,4,Paint()..color=cyan);
  }
  @override
  bool shouldRepaint(covariant MiniAgentLinks old) => old.t != t;
}

class GridPainter extends CustomPainter {
  @override
  void paint(Canvas c, Size s) {
    final p = Paint()..color = cyan.withOpacity(.045)..strokeWidth = 1;
    for(double x=0;x<s.width;x+=34){c.drawLine(Offset(x,0),Offset(x,s.height),p);}
    for(double y=0;y<s.height;y+=34){c.drawLine(Offset(0,y),Offset(s.width,y),p);}
  }
  @override bool shouldRepaint(covariant CustomPainter oldDelegate)=>false;
}

class OrbPainter extends CustomPainter {
  final double t; OrbPainter(this.t);
  @override
  void paint(Canvas canvas, Size size) {
    final center=Offset(size.width*.53,size.height*.52);
    final r=size.width*.29;
    canvas.drawCircle(center,r*1.8,Paint()..shader=RadialGradient(colors:[cyan.withOpacity(.22),blue.withOpacity(.07),Colors.transparent]).createShader(Rect.fromCircle(center:center,radius:r*1.8)));
    canvas.drawCircle(center,r,Paint()..shader=const RadialGradient(colors:[Color(0xFF65FFF0),Color(0xFF00BFAF),Color(0xFF126B91),Color(0xFF101D42)],center: Alignment(-.35,-.4),radius:.95).createShader(Rect.fromCircle(center:center,radius:r)));
    final orbit=Paint()..style=PaintingStyle.stroke..strokeWidth=1.5;
    for(int i=0;i<3;i++){
      canvas.save(); canvas.translate(center.dx,center.dy); canvas.rotate(t*math.pi*2+i*math.pi/3);
      canvas.drawOval(Rect.fromCenter(center:Offset.zero,width:r*3.1,height:r*.9),orbit..color=[cyan,violet,blue][i].withOpacity(.7));
      canvas.restore();
    }
    for(int i=0;i<9;i++){
      final a=t*math.pi*2+i*math.pi*2/9;
      final p=Offset(center.dx+math.cos(a)*r*1.55,center.dy+math.sin(a)*r*.65);
      canvas.drawCircle(p,3.2,Paint()..color=i.isEven?cyan:violet);
    }
  }
  @override bool shouldRepaint(covariant OrbPainter old)=>old.t!=t;
}

class NetworkPainter extends CustomPainter {
  final double t; final int selected;
  NetworkPainter(this.t,this.selected);
  @override
  void paint(Canvas canvas, Size s) {
    final center=Offset(s.width*.5,s.height*.49);
    final colors=[cyan,blue,violet];
    final nodes=[Offset(s.width*.5,s.height*.19),Offset(s.width*.22,s.height*.69),Offset(s.width*.78,s.height*.69)];
    final links=Paint()..color=cyan.withOpacity(.28)..strokeWidth=1.2;
    for(int i=0;i<3;i++){
      canvas.drawLine(center,nodes[i],links..color=colors[i].withOpacity(.38));
      canvas.drawCircle(nodes[i],42,Paint()..color=colors[i].withOpacity(.08));
      canvas.drawCircle(nodes[i],31,Paint()..color=panel2..style=PaintingStyle.fill);
      canvas.drawCircle(nodes[i],31,Paint()..color=colors[i].withOpacity(.8)..style=PaintingStyle.stroke..strokeWidth=1.5);
      canvas.drawCircle(nodes[i],7,Paint()..color=colors[i]);
      final label=['FUTURES','SPOT','ALPHA'][i];
      final tp=TextPainter(text:TextSpan(text:label,style:TextStyle(color:colors[i],fontSize:9,fontWeight:FontWeight.bold,letterSpacing:1)),textDirection:TextDirection.ltr)..layout();
      tp.paint(canvas,Offset(nodes[i].dx-tp.width/2,nodes[i].dy+42));
      for(int j=0;j<3;j++){
        final f=((t+j*.27+i*.19)%1);
        final p=Offset.lerp(center,nodes[i],f)!;
        canvas.drawCircle(p,2.5,Paint()..color=colors[i]);
      }
    }
    canvas.drawCircle(center,57,Paint()..shader=RadialGradient(colors:[cyan.withOpacity(.28),blue.withOpacity(.08),Colors.transparent]).createShader(Rect.fromCircle(center:center,radius:57)));
    canvas.drawCircle(center,31,Paint()..shader=const RadialGradient(colors:[Color(0xFF62FFF1),Color(0xFF007C9D),Color(0xFF111A35)]).createShader(Rect.fromCircle(center:center,radius:31)));
    final tp=TextPainter(text:const TextSpan(text:'AI',style:TextStyle(color:Colors.white,fontSize:16,fontWeight:FontWeight.w900)),textDirection:TextDirection.ltr)..layout();
    tp.paint(canvas,Offset(center.dx-tp.width/2,center.dy-tp.height/2));
  }
  @override bool shouldRepaint(covariant NetworkPainter old)=>old.t!=t||old.selected!=selected;
}

class CandlePainter extends CustomPainter {
  final double zoom, drag; CandlePainter(this.zoom,this.drag);
  @override
  void paint(Canvas canvas, Size s) {
    final grid=Paint()..color=Colors.white.withOpacity(.055)..strokeWidth=1;
    for(int i=0;i<5;i++){final y=s.height*i/4;canvas.drawLine(Offset(0,y),Offset(s.width,y),grid);}
    for(int i=0;i<6;i++){final x=s.width*i/5;canvas.drawLine(Offset(x,0),Offset(x,s.height),grid);}
    final int count=(28*zoom).round().clamp(18,58).toInt();
    final double step=s.width/count;
    final base=s.height*.53;
    for(int i=0;i<count;i++){
      final x=(i*step+step*.5+drag)%(s.width+step);
      final wave=math.sin(i*.72)*s.height*.10+math.sin(i*.19)*s.height*.16;
      final open=base-wave+math.sin(i*1.7)*10;
      final close=open+math.sin(i*1.13+1)*s.height*.13;
      final high=(math.min(open,close)-5-(i%4)*2).toDouble();
      final low=(math.max(open,close)+5+(i%3)*2).toDouble();
      final up=close<open;
      final color=up?green:red;
      final p=Paint()..color=color..strokeWidth=1.4;
      canvas.drawLine(Offset(x,high),Offset(x,low),p);
      final rect=Rect.fromLTRB(x-step*.27,math.min(open,close),x+step*.27,math.max(open,close)+.8);
      canvas.drawRect(rect,Paint()..color=color.withOpacity(.88));
    }
    final y=s.height*.32;
    final line=Paint()..color=cyan.withOpacity(.7)..strokeWidth=1..style=PaintingStyle.stroke;
    for(double x=0;x<s.width;x+=7){canvas.drawLine(Offset(x,y),Offset(x+3,y),line);}
    final label=RRect.fromRectAndRadius(Rect.fromLTWH(s.width-72,y-10,68,19),const Radius.circular(5));
    canvas.drawRRect(label,Paint()..color=cyan);
    final tp=TextPainter(text:const TextSpan(text:'67,420',style:TextStyle(color:bg,fontSize:9,fontWeight:FontWeight.bold)),textDirection:TextDirection.ltr)..layout();
    tp.paint(canvas,Offset(s.width-68,y-7));
  }
  @override bool shouldRepaint(covariant CandlePainter old)=>old.zoom!=zoom||old.drag!=drag;
}

class EquityPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size s) {
    final path=Path()..moveTo(0,s.height*.75);
    for(int i=1;i<=40;i++){final x=s.width*i/40;final y=s.height*(.7-.28*(i/40)+math.sin(i*.7)*.08+math.sin(i*.17)*.04);path.lineTo(x,y);}
    final fill=Path.from(path)..lineTo(s.width,s.height)..lineTo(0,s.height)..close();
    canvas.drawPath(fill,Paint()..shader=LinearGradient(colors:[cyan.withOpacity(.25),cyan.withOpacity(0)],begin:Alignment.topCenter,end:Alignment.bottomCenter).createShader(Offset.zero& s));
    canvas.drawPath(path,Paint()..color=cyan..style=PaintingStyle.stroke..strokeWidth=2);
  }
  @override bool shouldRepaint(covariant CustomPainter old)=>false;
}
class DonutPainter extends CustomPainter {
  @override
  void paint(Canvas c,Size s){
    final rect=Rect.fromLTWH(8,8,s.width-16,s.height-16);
    c.drawArc(rect,-math.pi/2,math.pi*2-.08,false,Paint()..color=cyan..style=PaintingStyle.stroke..strokeWidth=13..strokeCap=StrokeCap.round);
    c.drawArc(rect,math.pi*1.5,math.pi*.0,false,Paint()..color=blue..style=PaintingStyle.stroke..strokeWidth=13);
    final tp=TextPainter(text:const TextSpan(text:'100%',style:TextStyle(color:Colors.white,fontSize:17,fontWeight:FontWeight.w900)),textDirection:TextDirection.ltr)..layout();
    tp.paint(c,Offset((s.width-tp.width)/2,(s.height-tp.height)/2));
  }
  @override bool shouldRepaint(covariant CustomPainter old)=>false;
}
