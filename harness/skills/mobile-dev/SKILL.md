---
name: mobile-dev
description: >
  移动端开发 Skill。提供 iOS/Swift 和 Android/Kotlin 双平台开发模板、跨平台桥接规范、
  Flutter 组件模式。内置 SwiftUI ViewController、Jetpack Compose、Platform Channel 桥接代码模板，
  适用移动端功能开发、跨平台集成和 App Store 上架合规检查场景。
---

# mobile-dev — 移动端开发 Skill

## 核心能力

1. **iOS 开发**：Swift/SwiftUI、UIKit、Core Data
2. **Android 开发**：Kotlin/Jetpack Compose、View 系统
3. **跨平台桥接**：React Native/Flutter 组件集成
4. **性能优化**：启动速度、帧率、内存占用
5. **上架规范**：App Store/Google Play 合规要求

## iOS 组件模板

### SwiftUI View

```swift
import SwiftUI

struct UserProfileView: View {
    @StateObject private var viewModel = UserProfileViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Header
                AsyncImage(url: viewModel.user?.avatarURL) { image in
                    image.resizable()
                        .aspectRatio(contentMode: .fill)
                } placeholder: {
                    Circle().fill(Color.gray.opacity(0.3))
                }
                .frame(width: 80, height: 80)
                .clipShape(Circle())

                // Info
                Text(viewModel.user?.name ?? "未登录")
                    .font(.title2.bold())

                // Actions
                Button("保存") {
                    Task { await viewModel.save() }
                }
                .disabled(!viewModel.isModified)
            }
            .padding()
        }
        .task {
            await viewModel.load()
        }
        .alert("保存失败", isPresented: $viewModel.showError) {
            Button("重试") { Task { await viewModel.save() } }
            Button("取消", role: .cancel) { }
        }
    }
}

@MainActor
class UserProfileViewModel: ObservableObject {
    @Published var user: User?
    @Published var isModified = false
    @Published var showError = false

    func load() async {
        // Load user data
    }

    func save() async {
        // Save user data
    }
}
```

### UIKit ViewController

```swift
import UIKit

class UserProfileViewController: UIViewController {
    private let viewModel: UserProfileViewModel
    private lazy var tableView = UITableView(frame: .zero, style: .insetGrouped)

    init(viewModel: UserProfileViewModel) {
        self.viewModel = viewModel
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        setupUI()
        bindViewModel()
    }

    private func setupUI() {
        title = "个人资料"
        view.backgroundColor = .systemBackground

        tableView.delegate = self
        tableView.dataSource = self
        tableView.register(UITableViewCell.self, forCellReuseIdentifier: "cell")
        tableView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(tableView)

        NSLayoutConstraint.activate([
            tableView.topAnchor.constraint(equalTo: view.topAnchor),
            tableView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            tableView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            tableView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
        ])
    }
}
```

## Android 组件模板

### Jetpack Compose

```kotlin
@Composable
fun UserProfileScreen(
    viewModel: UserProfileViewModel = viewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.load()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        AsyncImage(
            model = uiState.user?.avatarUrl,
            contentDescription = "头像",
            modifier = Modifier
                .size(80.dp)
                .clip(CircleShape)
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = uiState.user?.name ?: "未登录",
            style = MaterialTheme.typography.titleLarge
        )

        Spacer(modifier = Modifier.weight(1f))

        Button(
            onClick = { viewModel.save() },
            enabled = uiState.isModified
        ) {
            Text("保存")
        }
    }

    if (uiState.isLoading) {
        CircularProgressIndicator()
    }

    uiState.error?.let { error ->
        Snackbar(
            modifier = Modifier.padding(16.dp)
        ) {
            Text(error.message)
        }
    }
}

@HiltViewModel
class UserProfileViewModel @Inject constructor(
    private val userRepository: UserRepository
) : ViewModel() {
    private val _uiState = MutableStateFlow(UserProfileUiState())
    val uiState: StateFlow<UserProfileUiState> = _uiState.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true) }
            try {
                val user = userRepository.getCurrentUser()
                _uiState.update { it.copy(user = user, isLoading = false) }
            } catch (e: Exception) {
                _uiState.update { it.copy(error = e, isLoading = false) }
            }
        }
    }
}
```

## 跨平台桥接

### Flutter 集成 iOS/Android

```dart
// Flutter Platform Channel
class NativeBridge {
    static const platform = MethodChannel('com.app/native');

    Future<String?> getDeviceToken() async {
        return await platform.invokeMethod('getDeviceToken');
    }

    Future<void> trackEvent(String name, Map<String, dynamic> params) async {
        await platform.invokeMethod('trackEvent', {'name': name, ...params});
    }
}

// iOS 实现
@objc class NativeBridge: NSObject, FlutterPlugin {
    static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(name: "com.app/native", binaryMessenger: registrar.messenger())
        let instance = NativeBridge()
        registrar.addMethodCallDelegate(instance, channel: channel)
    }

    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "getDeviceToken":
            result(UIDevice.current.identifierForVendor?.uuidString)
        default:
            result(FlutterMethodNotImplemented)
        }
    }
}
```

## 性能优化检查清单

| 检查项 | iOS | Android |
|-------|-----|---------|
| 启动速度 | Cold <2s | Cold <2s |
| 帧率 | 60fps | 60fps |
| 内存 | <150MB | <150MB |
| 包体积 | <30MB | <20MB |
| 电量 | 后台无活动 | Background WorkManager 管控 |

```swift
// iOS 启动优化：懒加载非必要模块
extension AppDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // 仅初始化必要模块
        CoreServices.shared.initEssential()
        return true
    }
}
```

```kotlin
// Android 启动优化：WorkManager 延迟加载
class App : Application() {
    override fun onCreate() {
        super.onCreate()
        // 仅初始化必要模块
    }
}

// 延迟初始化非必要模块
WorkManager.getInstance(this).enqueue(
    OneTimeWorkRequestBuilder<AnalyticsInitWorker>().build()
)
```

## App Store / Google Play 上架规范

| 要求 | App Store | Google Play |
|------|----------|-------------|
| 截图 | 6.7寸 + 6.5寸（必须）| 手机 + 平板（各2张）|
| 隐私政策 | 必需（有用户数据时）| 必需（有敏感数据时）|
| 年龄分级 | 必需（4+ ~ 17+）| 必需（内容评级）|
| 开发者账号 | $99/年 | $25 一次性 |
| 审核时间 | 1-3 天 | 2-7 天 |

## 验证方法

```bash
[[ -f skills/mobile-dev/SKILL.md ]] && echo "✅"

grep -q "SwiftUI\|UIKit\|Jetpack.*Compose" skills/mobile-dev/SKILL.md && echo "✅ 跨平台模板"
grep -q "Platform.*Channel\|NativeBridge" skills/mobile-dev/SKILL.md && echo "✅ 桥接"
grep -q "App Store\|Google Play" skills/mobile-dev/SKILL.md && echo "✅ 上架规范"
```

## Red Flags

- 直接在主线程执行网络请求
- 无包体积控制导致 >100MB
- 内存泄漏（未释放资源）
- 无深链接处理
- 隐私政策缺失
