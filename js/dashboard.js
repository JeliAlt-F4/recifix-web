function toggleDashboardPassword(inputId, button) {

    const input =
        document.getElementById(inputId);

    if (!input) {
        return;
    }

    const showingPassword =
        input.type === "text";

    input.type = showingPassword ? "password" : "text";
    button.setAttribute(
        "aria-label",
        showingPassword ? "Show password" : "Hide password"
    );

}

document.addEventListener("DOMContentLoaded", function () {

    const themeToggle =
        document.querySelector(".theme-toggle");

    const currentView =
        new URLSearchParams(window.location.search).get("view");

    const activeView = ["pantry", "saved", "contact"].includes(currentView)
        ? currentView
        : "home";

    const pantryDashboard =
        document.querySelector(".dashboard-pantry");

    const homeDashboard =
        document.querySelector(".dashboard-home");

    const savedDashboard =
        document.querySelector(".dashboard-saved");

    const contactDashboard =
        document.querySelector(".dashboard-contact");

    const dashboardPage =
        document.querySelector(".dashboard-page");

    const homeLink =
        document.querySelector('.sidebar-nav a[href="dashboard.html?view=home"]');

    const pantryLink =
        document.querySelector('.sidebar-nav a[href="dashboard.html?view=pantry"]');

    const savedLink =
        document.querySelector('.sidebar-nav a[href="dashboard.html?view=saved"]');

    const contactLink =
        document.querySelector('.sidebar-nav a[href="dashboard.html?view=contact"]');

    const openPantryAction =
        document.querySelector(".home-dashboard-action");

    const generateRecipeButton =
        document.getElementById("generateRecipe");

    const pantryRecipeShowcase =
        document.getElementById("pantryRecipeShowcase");

    setDashboardView(activeView, false);

    function switchDashboardView(view) {

        dashboardPage.classList.add("view-switching");

        window.setTimeout(function () {

            setDashboardView(view, true);

            window.requestAnimationFrame(function () {
                dashboardPage.classList.remove("view-switching");
            });

        }, 180);

    }

    homeLink.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("home");
    });

    pantryLink.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("pantry");

    });

    savedLink.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("saved");
    });

    contactLink.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("contact");
    });

    openPantryAction.addEventListener("click", function (event) {
        event.preventDefault();
        switchDashboardView("pantry");
    });

    window.addEventListener("popstate", function () {
        const view = new URLSearchParams(window.location.search).get("view");
        setDashboardView(["pantry", "saved", "contact"].includes(view) ? view : "home", false);
    });

    const savedTheme =
        localStorage.getItem("recifix-theme");

    const initialTheme =
        savedTheme === "dark"
            ? "dark"
            : "light";

    function updateThemeButton() {

        const darkMode =
            document.body.classList.contains("dark-mode");

        document.documentElement.classList.toggle(
            "dark-mode",
            darkMode
        );

        themeToggle.setAttribute(
            "aria-pressed",
            String(darkMode)
        );

        themeToggle.setAttribute(
            "aria-label",
            darkMode
                ? "Switch to light mode"
                : "Switch to dark mode"
        );

        themeToggle.querySelector("img").src =
            darkMode
                ? "images/icons/darkmode.svg"
                : "images/icons/lightmode.svg";

    }

    document.body.classList.toggle(
        "dark-mode",
        initialTheme === "dark"
    );

    localStorage.setItem(
        "recifix-theme",
        initialTheme
    );

    if (initialTheme === "dark") {

        document.body.classList.add("dark-mode");

    }

    updateThemeButton();

    themeToggle.addEventListener("click", function () {

        document.body.classList.toggle("dark-mode");

        localStorage.setItem(
            "recifix-theme",
            document.body.classList.contains("dark-mode")
                ? "dark"
                : "light"
        );

        updateThemeButton();

    });

    const ingredientInput =
        document.getElementById("ingredientInput");

    const addIngredientButton =
        document.getElementById("addIngredient");

    const ingredientTags =
        document.getElementById("ingredientTags");

    const clearIngredientsButton =
        document.getElementById("clearIngredients");

    const profileButton =
        document.getElementById("profileButton");

    const logoutModal =
        document.getElementById("logoutModal");

    const closeLogoutButton =
        document.getElementById("closeLogout");

    const cancelLogoutButton =
        document.getElementById("cancelLogout");

    const profileGreeting =
        document.getElementById("profileGreeting");

    const profileInitial =
        document.getElementById("profileInitial");

    const accountTitle =
        document.getElementById("accountTitle");

    const accountEmail =
        document.getElementById("accountEmail");

    const accountAvatar =
        document.getElementById("accountAvatar");

    const openChangePasswordButton =
        document.getElementById("openChangePassword");

    const changePasswordForm =
        document.getElementById("changePasswordForm");

    const dashboardCurrentPassword =
        document.getElementById("dashboardCurrentPassword");

    const changePasswordMessage =
        document.getElementById("changePasswordMessage");

    const cancelChangePasswordButton =
        document.getElementById("cancelChangePassword");

    const openTwoFactorButton =
        document.getElementById("openTwoFactor");

    const twoFactorForm =
        document.getElementById("twoFactorForm");

    const twoFactorSummary =
        document.getElementById("twoFactorSummary");

    const twoFactorMessage =
        document.getElementById("twoFactorMessage");

    const twoFactorQr =
        document.getElementById("twoFactorQr");

    const twoFactorCode =
        document.getElementById("twoFactorCode");

    const cancelTwoFactorButton =
        document.getElementById("cancelTwoFactor");

    const saveTwoFactorButton =
        document.getElementById("saveTwoFactor");

    let twoFactorEnabled = false;
    let pendingTwoFactorSecret = null;

    const queryUser =
        new URLSearchParams(window.location.search);

    let storedUser = {};

    try {
        storedUser = JSON.parse(
            localStorage.getItem("recifix-user") || "{}"
        ) || {};
    } catch {}

    if (typeof storedUser !== "object") {
        storedUser = {};
    }

    if (Object.prototype.hasOwnProperty.call(storedUser, "password")) {
        delete storedUser.password;
        localStorage.setItem("recifix-user", JSON.stringify(storedUser));
    }

    let accountName =
        storedUser.name || "Your account";

    let accountEmailAddress =
        storedUser.email || "";

    function renderAccountDetails() {

        const hasName =
            accountName !== "Your account";

        const initial =
            hasName
                ? accountName.charAt(0).toUpperCase()
                : "?";

        profileGreeting.textContent =
            hasName
                ? "Hi, " + accountName.split(" ")[0]
                : "Hi";

        profileInitial.textContent = initial;
        accountTitle.textContent = accountName;
        accountEmail.textContent = accountEmailAddress || "Email not set";
        accountAvatar.textContent = initial;
        if (twoFactorSummary) {
            twoFactorSummary.textContent = twoFactorEnabled
                ? "On — required at login"
                : "Off — add an authenticator app";
        }
        if (saveTwoFactorButton) {
            saveTwoFactorButton.textContent = twoFactorEnabled ? "Turn off" : "Turn on";
        }
    }

    function applyUser(user) {

        accountName = user.name;
        accountEmailAddress = user.email;

        localStorage.setItem(
            "recifix-user",
            JSON.stringify({ name: user.name, email: user.email })
        );

        renderAccountDetails();

    }

    function sessionExpired() {

        localStorage.removeItem("recifix-user");
        window.location.replace("pages/login.html");

    }

    renderAccountDetails();

    recifixApi("/api/auth/me").then(function (result) {

        if (result.status === 401) {
            sessionExpired();
            return;
        }

        if (result.ok) {
            twoFactorEnabled = Boolean(result.data.user.two_factor_enabled);
            applyUser(result.data.user);
        }

    });

    function closeLogoutModal() {

        logoutModal.classList.remove("show");

        logoutModal.setAttribute("aria-hidden", "true");

    }

    profileButton.addEventListener("click", function () {

        logoutModal.classList.add("show");

        logoutModal.setAttribute("aria-hidden", "false");

    });

    closeLogoutButton.addEventListener(
        "click",
        closeLogoutModal
    );

    cancelLogoutButton.addEventListener(
        "click",
        closeLogoutModal
    );

    openChangePasswordButton.addEventListener("click", function () {

        changePasswordForm.hidden = false;
        openChangePasswordButton.hidden = true;
        changePasswordForm.reset();
        recifixShowMessage(changePasswordMessage, "");
        dashboardCurrentPassword.focus();

    });

    cancelChangePasswordButton.addEventListener("click", function () {

        changePasswordForm.hidden = true;
        openChangePasswordButton.hidden = false;

    });

    function closeTwoFactorForm() {
        twoFactorForm.hidden = true;
        openTwoFactorButton.hidden = false;
        pendingTwoFactorSecret = null;
        if (twoFactorQr) {
            twoFactorQr.hidden = true;
            twoFactorQr.removeAttribute("src");
        }
    }

    openTwoFactorButton.addEventListener("click", async function () {
        changePasswordForm.hidden = true;
        openChangePasswordButton.hidden = false;
        twoFactorForm.hidden = false;
        openTwoFactorButton.hidden = true;
        twoFactorForm.reset();
        recifixShowMessage(twoFactorMessage, "");
        pendingTwoFactorSecret = null;
        twoFactorQr.hidden = true;

        if (twoFactorEnabled) {
            recifixShowMessage(
                twoFactorMessage,
                "Enter a current authenticator code to turn this off.",
                true
            );
            twoFactorCode.focus();
            return;
        }

        saveTwoFactorButton.disabled = true;
        const setup = await recifixApi("/api/account/2fa/setup", { method: "POST" });
        saveTwoFactorButton.disabled = false;
        if (setup.status === 401) {
            sessionExpired();
            return;
        }
        if (!setup.ok) {
            recifixShowMessage(twoFactorMessage, setup.data.error || "Could not start authenticator setup.");
            return;
        }
        pendingTwoFactorSecret = setup.data.secret;
        twoFactorQr.src = "https://api.qrserver.com/v1/create-qr-code/?data="
            + encodeURIComponent(setup.data.otpauth_url)
            + "&size=160x160";
        twoFactorQr.hidden = false;
        recifixShowMessage(
            twoFactorMessage,
            "Scan the QR code, then enter the 6-digit code to finish.",
            true
        );
        twoFactorCode.focus();
    });

    cancelTwoFactorButton.addEventListener("click", closeTwoFactorForm);

    saveTwoFactorButton.addEventListener("click", async function () {
        const code = twoFactorCode.value.trim();
        if (!/^\d{6}$/.test(code)) {
            recifixShowMessage(twoFactorMessage, "Enter the 6-digit code from your authenticator app.");
            return;
        }
        saveTwoFactorButton.disabled = true;
        const result = twoFactorEnabled
            ? await recifixApi("/api/account/2fa/disable", { method: "POST", body: { code: code } })
            : await recifixApi("/api/account/2fa/verify", {
                method: "POST",
                body: { secret: pendingTwoFactorSecret, code: code }
            });
        saveTwoFactorButton.disabled = false;
        if (result.status === 401) {
            sessionExpired();
            return;
        }
        if (!result.ok) {
            recifixShowMessage(twoFactorMessage, result.data.error || "Could not update two-factor authentication.");
            return;
        }
        twoFactorEnabled = Boolean(result.data.user && result.data.user.two_factor_enabled);
        renderAccountDetails();
        closeTwoFactorForm();
    });

    async function saveNewPassword() {

        const saveButton =
            changePasswordForm.querySelector(".confirm-logout");

        const currentPassword = dashboardCurrentPassword.value;

        const newPassword =
            document.getElementById("dashboardNewPassword").value;

        const confirmPassword =
            document.getElementById("dashboardConfirmPassword").value;

        if (!currentPassword) {
            recifixShowMessage(changePasswordMessage, "Enter your current password.");
            return;
        }

        if (newPassword.length < 8) {
            recifixShowMessage(changePasswordMessage, "New password must be at least 8 characters.");
            return;
        }

        if (newPassword !== confirmPassword) {
            recifixShowMessage(changePasswordMessage, "The new passwords don't match.");
            return;
        }

        saveButton.disabled = true;

        const result = await recifixApi("/api/account/password", {
            method: "POST",
            body: {
                current_password: currentPassword,
                new_password: newPassword
            }
        });

        saveButton.disabled = false;

        if (result.status === 401) {
            sessionExpired();
            return;
        }

        if (!result.ok) {
            recifixShowMessage(
                changePasswordMessage,
                result.data.error || "Could not update your password."
            );
            return;
        }

        changePasswordForm.reset();
        recifixShowMessage(changePasswordMessage, "Password updated.", true);

    }

    changePasswordForm.addEventListener("submit", function (event) {
        event.preventDefault();
        saveNewPassword();
    });

    changePasswordForm
        .querySelector(".confirm-logout")
        .addEventListener("click", saveNewPassword);

    const confirmLogoutButton =
        document.getElementById("confirmLogout");

    confirmLogoutButton.addEventListener("click", async function () {

        confirmLogoutButton.disabled = true;

        await recifixApi("/api/auth/logout", { method: "POST" });

        localStorage.removeItem("recifix-user");
        window.location.replace("index.html");

    });

    logoutModal.addEventListener("click", function (event) {

        if (event.target === logoutModal) {

            closeLogoutModal();

        }

    });

    function addIngredient() {

        const value =
            ingredientInput.value.trim();

        if (value === "") {

            ingredientInput.focus();

            return;

        }

        const existingTags =
            ingredientTags.querySelectorAll(
                ".ingredient-tag"
            );

        const alreadyExists =
            Array.from(existingTags).some(
                function (tag) {

                    const ingredientName =
                        tag.firstChild
                            .textContent
                            .trim();

                    return (
                        ingredientName.toLowerCase() ===
                        value.toLowerCase()
                    );

                }
            );

        if (alreadyExists) {

            ingredientInput.value = "";

            ingredientInput.focus();

            return;

        }

        const tag =
            document.createElement("button");

        tag.type = "button";

        tag.className =
            "ingredient-tag";

        const ingredientName =
            value.charAt(0).toUpperCase() +
            value.slice(1);

        const text =
            document.createTextNode(
                ingredientName
            );

        const remove =
            document.createElement("span");

        remove.className =
            "remove-tag";

        remove.textContent =
            "×";

        tag.appendChild(text);

        tag.appendChild(remove);

        ingredientTags.appendChild(tag);

        clearIngredientsButton.disabled = false;

        ingredientInput.value = "";

        ingredientInput.focus();

    }

    addIngredientButton.addEventListener(
        "click",
        addIngredient
    );

    ingredientInput.addEventListener(
        "keydown",
        function (event) {

            if (event.key === "Enter") {

                event.preventDefault();

                addIngredient();

            }

        }
    );

    ingredientTags.addEventListener(
        "click",
        function (event) {

            if (
                event.target.classList.contains(
                    "remove-tag"
                )
            ) {

                event.preventDefault();

                event.stopPropagation();

                event.target.closest(
                    ".ingredient-tag"
                ).remove();

                clearIngredientsButton.disabled =
                    ingredientTags.querySelector(
                        ".ingredient-tag"
                    ) === null;

                return;

            }

            const tag =
                event.target.closest(
                    ".ingredient-tag"
                );

            if (!tag) {

                return;

            }

        }
    );

    clearIngredientsButton.addEventListener(
        "click",
        function () {

            ingredientTags.replaceChildren();

            clearIngredientsButton.disabled = true;

        }
    );

    const filterPills =
        document.querySelectorAll(
            ".filter-pill"
        );

    const filterToneByName = {
        vegan: "tone-vegan",
        vegetarian: "tone-vegetarian",
        halal: "tone-teal",
        spicy: "tone-coral",
        savory: "tone-savory",
        sweet: "tone-gold",
        mild: "tone-blue",
        tangy: "tone-coral",
        sour: "tone-gold",
        nuts: "tone-nuts",
        dairy: "tone-dairy",
        eggs: "tone-eggs",
        seafood: "tone-seafood",
        gluten: "tone-gluten",
        soy: "tone-soy",
        shellfish: "tone-shellfish",
        sesame: "tone-sesame",
        breakfast: "tone-gold",
        lunch: "tone-lunch",
        dinner: "tone-night",
        dessert: "tone-pink"
    };

    filterPills.forEach(function (pill) {

        const tone =
            filterToneByName[
                pill.textContent.trim().toLowerCase()
            ];

        if (tone) {

            pill.classList.add(tone);

        }

    });

    filterPills.forEach(
        function (pill) {

            pill.addEventListener(
                "click",
                function () {
                    pill.classList.toggle(
                        "selected"
                    );

                }
            );

        }
    );

    const adoboRecipeModal =
        document.getElementById("adoboRecipeModal");

    const closeAdoboRecipe =
        document.getElementById("closeAdoboRecipe");

    function setAdoboRecipeModal(open) {
        adoboRecipeModal.classList.toggle("is-open", open);
        adoboRecipeModal.setAttribute("aria-hidden", String(!open));
        document.body.classList.toggle("recipe-modal-open", open);
    }

    window.recifixSetRecipeModal = setAdoboRecipeModal;

    closeAdoboRecipe.addEventListener("click", function () {
        setAdoboRecipeModal(false);
    });

    adoboRecipeModal.addEventListener("click", function (event) {
        if (event.target === adoboRecipeModal) {
            setAdoboRecipeModal(false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && adoboRecipeModal.classList.contains("is-open")) {
            setAdoboRecipeModal(false);
        }
    });

    
    function setDashboardView(view, updateUrl) {

        const showHome = view === "home";
        const showPantry = view === "pantry";

        pantryDashboard.hidden = !showPantry;
        homeDashboard.hidden = !showHome;
        savedDashboard.hidden = view !== "saved";
        contactDashboard.hidden = view !== "contact";
        document.documentElement.classList.toggle("home-view", showHome);
        homeLink.classList.toggle("active", showHome);
        pantryLink.classList.toggle("active", showPantry);
        savedLink.classList.toggle("active", view === "saved");
        contactLink.classList.toggle("active", view === "contact");
        document.dispatchEvent(new CustomEvent("recifix:viewchange", { detail: { view: view } }));

        if (updateUrl) {
            window.history.pushState(
                {},
                "",
                "dashboard.html?view=" + view
            );
        }

         //  TIMED AUTOMATED CORRELATION TRIGGER
        if (showHome) {
            window.setTimeout(function() {
                if (typeof loadHomeScreenRecommendations === "function") {
                    loadHomeScreenRecommendations();
                }
            }, 50);
        }
    }   

    // ========================================================
    //  DASHBOARD CONTACT FORM HANDLER
    // ========================================================
    (function() {
        const dashboardContactForm = document.getElementById("dashboardContactForm");
        if (dashboardContactForm) {
            dashboardContactForm.addEventListener("submit", async function(event) {
                event.preventDefault();

                const submitBtn = dashboardContactForm.querySelector("button[type='submit']");
                const subjectInput = document.getElementById("dashboardContactSubject");
                const messageInput = document.getElementById("dashboardContactMessage");

                const subject = subjectInput ? subjectInput.value.trim() : "";
                const message = messageInput ? messageInput.value.trim() : "";

                // Show loading state
                submitBtn.textContent = "Sending...";
                submitBtn.disabled = true;

                try {
                    // Get user info from localStorage to include email/name
                    let storedUser = {};
                    try {
                        storedUser = JSON.parse(localStorage.getItem("recifix-user") || "{}");
                    } catch {}

                    const response = await fetch("/api/contact", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            name: storedUser.name || "",
                            email: storedUser.email || "dashboard_user@recifix.local",
                            subject: subject,
                            body: message
                        })
                    });

                    const data = await response.json();

                    if (data.ok) {
                        // Show success message inline like landing page
                        const successDiv = document.createElement("div");
                        successDiv.className = "form-success-message";
                        successDiv.style.cssText = "background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 12px; border-radius: 6px; margin-bottom: 15px; text-align: center;";
                        successDiv.textContent = data.message || "Message sent successfully! We'll get back to you soon.";
                        dashboardContactForm.insertBefore(successDiv, dashboardContactForm.firstChild);

                        // Clear form
                        dashboardContactForm.reset();

                        // Remove success message after 5 seconds
                        setTimeout(function() {
                            if (successDiv.parentNode) {
                                successDiv.parentNode.removeChild(successDiv);
                            }
                        }, 5000);
                    } else {
                        alert(data.error || "Failed to send message. Please try again.");
                    }
                } catch (err) {
                    alert("Network error. Please check your connection and try again.");
                } finally {
                    submitBtn.innerHTML = "Send message <span aria-hidden='true'>&#8594;</span>";
                    submitBtn.disabled = false;
                }
            });
        }
    })();

    // ========================================================
    //  USER HISTORY & SAVED-BASED ML RECIPES FETCHER
    // ========================================================
    async function loadHomeScreenRecommendations() {
        // 🔍 target the correct HTML ID element from your Home view markup
        const homeGrid = document.getElementById("homeRecipeRecommendationsGrid");
        if (!homeGrid) return;

        try {
            const response = await fetch("/api/recipes/recommend", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({})
            });

            const data = await response.json();

            if (data.error || !data.recipes || data.recipes.length === 0) {
                homeGrid.innerHTML = '<div style="padding: 20px; color: var(--ref-muted, #888); text-align: center;">Save a few recipes to unlock hyper-personalized taste matching choices here!</div>';
                return;
            }

            // Clear the "Querying..." loading placeholder text instantly
            homeGrid.innerHTML = "";

            // Dynamically alter subheadings based on history personalization states
            const subtitleElement = document.querySelector(".ml-recommendations-section p");
            if (subtitleElement) {
                subtitleElement.textContent = data.personalized 
                    ? "Tailored recipe discoveries matching flavors and parameters from your collection."
                    : "Popular recipes matching standard pantry staples in your kitchen right now.";
            }

            data.recipes.forEach(recipe => {
                const card = document.createElement("article");
                card.className = "recipe-card";

                const badgeLabel = data.personalized ? "✦ For You" : "✦ Popular Option";
                const badgeBg = data.personalized ? "#e0f2fe" : "#eafaf1";
                const badgeColor = data.personalized ? "#0369a1" : "#2e7d32";

                const imageSrc = recipe.image ? recipe.image : "images/intro-image.jpg";

                // 1. Image Container (fixed height 160px to prevent overflow)
                const imgContainer = document.createElement("div");
                imgContainer.style.cssText = "width: 100%; height: 160px; overflow: hidden; border-radius: 8px; margin-bottom: 14px; background: #f1f5f9;";

                const imageEl = document.createElement("img");
                imageEl.style.cssText = "width: 100%; height: 100%; object-fit: cover;";
                imageEl.alt = recipe.title || "";
                imageEl.src = imageSrc;
                imgContainer.appendChild(imageEl);

                // 2. Badge & Percentage Row
                const badgeDiv = document.createElement("div");
                badgeDiv.style.cssText = "display: flex; justify-content: space-between; align-items: center;";

                const badgeSpan = document.createElement("span");
                badgeSpan.style.cssText = `background: ${badgeBg}; color: ${badgeColor}; font-size: 0.75rem; font-weight: 600; padding: 4px 10px; border-radius: 12px;`;
                badgeSpan.textContent = badgeLabel;

                const percSpan = document.createElement("span");
                percSpan.style.cssText = "font-size: 0.75rem; color: var(--ref-muted, #718181); font-weight: 600;";
                percSpan.textContent = `${recipe.match_percentage}% Match`;

                badgeDiv.append(badgeSpan, percSpan);

                // 3. Title (XSS safe textContent)
                const titleEl = document.createElement("h3");
                titleEl.style.cssText = "margin: 12px 0 6px 0; font-family: 'Playfair Display', serif; font-size: 1.4rem; color: #1e293b;";
                titleEl.textContent = recipe.title || "";

                // 4. Description
                const para = document.createElement("p");
                para.style.cssText = "font-size: 0.9rem; color: #64748b; line-height: 1.5; margin: 0 0 16px 0;";
                para.textContent = data.personalized
                    ? 'Matches ingredients and flavor profiles from recipes you saved recently.'
                    : 'A classic recipe choice perfectly suited to common household kitchen items.';

                // 5. Button (uses margin-top: auto from CSS)
                const button = document.createElement("button");
                button.type = "button";
                button.className = "view-recipe-btn";
                button.textContent = "View Recipe";

                // Append everything directly to the card (which is a flex column)
                card.append(imgContainer, badgeDiv, titleEl, para, button);

                // Safe click listener that hooks directly into your site's native popup engine!
                button.addEventListener("click", function() {
                    if (typeof window.recifixOpenRecipeModalGlobal === "function") {
                        window.recifixOpenRecipeModalGlobal(recipe.id);
                    } else {
                        alert("The recipe module layout engine is still loading. Please try again in a second!");
                    }
                });

                homeGrid.appendChild(card);
            });

        } catch (error) {
            console.error("Home view personalized ML fetch failure:", error);
            homeGrid.innerHTML = '<div style="color: red; padding: 20px; text-align: center;">Unable to connect to the recommendation engine.</div>';
        }
    }

});
