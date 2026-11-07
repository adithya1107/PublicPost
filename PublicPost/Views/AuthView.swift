import SwiftUI

/// Login / register form, shown as a sheet. Guests can dismiss it and keep reading.
struct AuthView: View {
    @State private var viewModel: AuthViewModel
    @Environment(\.dismiss) private var dismiss

    /// Why the user is being asked to log in, e.g. "Log in to vote on stories." (optional).
    let reason: String?

    init(auth: AuthManager, reason: String? = nil) {
        _viewModel = State(initialValue: AuthViewModel(auth: auth))
        self.reason = reason
    }

    var body: some View {
        NavigationStack {
            Form {
                if let reason {
                    Section {
                        Label(reason, systemImage: "lock")
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    Picker("Mode", selection: $viewModel.mode) {
                        ForEach(AuthViewModel.Mode.allCases) { mode in
                            Text(mode.rawValue).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets())
                }

                Section {
                    if viewModel.mode == .register {
                        TextField("Display name", text: $viewModel.displayName)
                            .textContentType(.nickname)
                    }
                    TextField("Email", text: $viewModel.email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Password", text: $viewModel.password)
                        .textContentType(viewModel.mode == .login ? .password : .newPassword)
                } footer: {
                    if let hint = viewModel.validationHint {
                        Text(hint)
                    }
                }

                if let message = viewModel.errorMessage {
                    Section {
                        Label(message, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }

                Section {
                    Button {
                        Task {
                            if await viewModel.submit() { dismiss() }
                        }
                    } label: {
                        HStack {
                            Spacer()
                            if viewModel.isSubmitting {
                                ProgressView()
                            } else {
                                Text(viewModel.mode.rawValue).fontWeight(.semibold)
                            }
                            Spacer()
                        }
                    }
                    .disabled(!viewModel.canSubmit)
                } footer: {
                    if viewModel.mode == .login {
                        Text("Demo account: demo@publicpost.app / password123")
                    }
                }
            }
            .navigationTitle(viewModel.mode.rawValue)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Continue as guest") { dismiss() }
                }
            }
        }
    }
}

#Preview("Login") {
    AuthView(auth: .preview(signedIn: false), reason: "Log in to vote on stories.")
}

#Preview("Register") {
    AuthView(auth: .preview(signedIn: false))
}
