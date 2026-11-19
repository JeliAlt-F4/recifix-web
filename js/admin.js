let members = [];
let recipes = [];
let messages = [];

const memberBody = document.querySelector("#membersTableBody");
const messageList = document.querySelector("#messageList");
const recipeBody = document.querySelector("#recipesTableBody");
const recipeEditorDialog = document.querySelector("#recipeEditorDialog");
const recipeEditorForm = document.querySelector("#recipeEditorForm");
const accountSettingsForm = document.querySelector("#accountSettingsForm");
let activeMemberFilter = "all";
let memberSearchQuery = "";
let memberPage = 1;
const membersPerPage = 10;
let activeMessageFilter = "all";
let editingRecipeId = null;

// Account modal popup
const accountButton = document.querySelector(".account-button");
const accountModal = document.querySelector("#adminAccountModal");
const accountClose = document.querySelector("[data-close-account]");
const accountLogoutBtn = document.querySelector("#adminAccountLogout");

function openAccountModal() {
    if (accountModal) {
        accountModal.hidden = false;
        accountModal.showModal();
    }
}

function closeAccountModal() {
    if (accountModal) {
        accountModal.hidden = true;
        accountModal.close();
    }
}

if (accountButton) {
    accountButton.addEventListener("click", (e) => {
        e.stopPropagation();
        openAccountModal();
    });
}

if (accountClose) {
    accountClose.addEventListener("click", closeAccountModal);
}

if (accountLogoutBtn) {
    accountLogoutBtn.addEventListener("click", async () => {
        closeAccountModal();
        await recifixApi("/api/auth/logout", { method: "POST" });
        localStorage.removeItem("recifix-user");
        window.location.href = "pages/login.html";
    });
}

if (accountModal) {
    accountModal.addEventListener("click", (e) => {
        if (e.target === accountModal) closeAccountModal();
    });
}

// Change password (inside account modal)
const accountChangePasswordBtn = document.querySelector("#adminAccountChangePassword");

if (accountChangePasswordBtn && accountModal) {
    accountChangePasswordBtn.addEventListener("click", () => {
        const content = accountModal.querySelector(".account-modal-content");
        if (!content || content.querySelector("#adminPasswordForm")) return;

        const form = document.createElement("form");
        form.id = "adminPasswordForm";
        form.className = "account-modal-body";
        form.innerHTML = `
            <div class="form-group" style="margin-bottom:12px;">
                <label for="adminCurrentPassword">Current password</label>
                <input type="password" id="adminCurrentPassword" autocomplete="current-password" required>
            </div>
            <div class="form-group" style="margin-bottom:12px;">
                <label for="adminNewPassword">New password</label>
                <input type="password" id="adminNewPassword" autocomplete="new-password" minlength="8" required>
            </div>
            <div class="form-group" style="margin-bottom:12px;">
                <label for="adminConfirmPassword">Confirm new password</label>
                <input type="password" id="adminConfirmPassword" autocomplete="new-password" minlength="8" required>
            </div>
            <p id="adminPasswordStatus" style="font-size:13px;margin:0 0 12px;" hidden></p>
            <div style="display:flex;gap:8px;">
                <button type="button" id="adminPasswordCancel" style="flex:1;padding:8px;border:1px solid #ddd;border-radius:8px;background:#fff;cursor:pointer;font-size:13px;font-weight:600;">Cancel</button>
                <button type="submit" style="flex:1;padding:8px;border:none;border-radius:8px;background:#8b4513;color:#fff;cursor:pointer;font-size:13px;font-weight:600;">Update password</button>
            </div>
        `;

        const originalBody = accountModal.querySelector(".account-modal-body");
        originalBody.hidden = true;
        content.appendChild(form);
        form.querySelector("#adminCurrentPassword").focus();

        function restoreModal() {
            form.remove();
            originalBody.hidden = false;
        }

        form.querySelector("#adminPasswordCancel").addEventListener("click", restoreModal);

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const status = form.querySelector("#adminPasswordStatus");
            const currentPassword = form.querySelector("#adminCurrentPassword").value;
            const newPassword = form.querySelector("#adminNewPassword").value;
            const confirmPassword = form.querySelector("#adminConfirmPassword").value;

            status.hidden = false;
            status.style.color = "#b3261e";

            if (newPassword.length < 8) {
                status.textContent = "New password must be at least 8 characters.";
                return;
            }
            if (newPassword !== confirmPassword) {
                status.textContent = "The new passwords don't match.";
                return;
            }

            const result = await recifixApi("/api/account/password", {
                method: "POST",
                body: { current_password: currentPassword, new_password: newPassword }
            });

            if (result.status === 401) {
                localStorage.removeItem("recifix-user");
                window.location.href = "pages/login.html";
                return;
            }

            if (!result.ok) {
                status.textContent = (result.data && result.data.error) || "Could not update your password.";
                return;
            }

            status.style.color = "#2e7d32";
            status.textContent = "Password updated.";
            setTimeout(restoreModal, 900);
        });
    });
}

// Update account modal with live user data
async function updateAccountModal() {
    const res = await recifixApi("/api/auth/me");
    if (res.ok && res.data.user) {
        const u = res.data.user;
        const avatar = document.querySelector("#adminAccountAvatar");
        const name = document.querySelector("#adminAccountName");
        const email = document.querySelector("#adminAccountEmail");
        const sidebarAvatar = document.querySelector(".sidebar-admin .avatar");
        const sidebarName = document.querySelector(".sidebar-admin strong");
        const sidebarRole = document.querySelector(".sidebar-admin small");

        if (avatar) avatar.textContent = (u.name || "A")[0].toUpperCase();
        if (name) name.textContent = u.name || "Administrator";
        if (email) email.textContent = u.email || "Email not set";
        if (sidebarAvatar) sidebarAvatar.textContent = (u.name || "A")[0].toUpperCase();
        if (sidebarName) sidebarName.textContent = u.name || "Admin";
        if (sidebarRole) sidebarRole.textContent = (u.role || "admin").charAt(0).toUpperCase() + (u.role || "admin").slice(1);
    }
}
updateAccountModal();

function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[character]);
}

async function loadStats() {
    const res = await recifixApi("/api/admin/stats");
    if (res.ok && res.data) {
        const totalUsers = Number(res.data.total_users);
        const totalUsersEl = document.querySelector("#totalUsers");
        if (Number.isFinite(totalUsers)) {
            if (totalUsersEl) totalUsersEl.textContent = totalUsers.toLocaleString();
            document.querySelectorAll(".nav-count").forEach((count) => {
                count.textContent = totalUsers.toLocaleString();
            });
        }
        const totalRecipesEl = document.querySelector("#totalRecipes");
        if (totalRecipesEl) totalRecipesEl.textContent = String(res.data.total_recipes).padStart(2, "0");
        const unreadEl = document.querySelector("#unreadCount");
        if (unreadEl) unreadEl.textContent = String(res.data.unread_messages).padStart(2, "0");
        const navDot = document.querySelector(".nav-dot");
        const unreadMessages = Number(res.data.unread_messages);
        if (navDot && Number.isFinite(unreadMessages)) navDot.hidden = unreadMessages === 0;
    }
}

function parseOverviewDate(value) {
    if (!value) return null;
    const raw = String(value);
    const normalized = /^\d{4}-\d{2}-\d{2} \d/.test(raw) ? `${raw.replace(" ", "T")}Z` : raw;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
}

function formatOverviewDate(value) {
    const date = parseOverviewDate(value);
    if (!date) return "Date unavailable";
    return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function overviewDateTime(value) {
    const date = parseOverviewDate(value);
    return date ? date.toISOString() : "";
}

function overviewActivityItem({ kind, label, title, description, date, href }) {
    const dateMarkup = date
        ? `<time datetime="${escapeHTML(overviewDateTime(date))}">${escapeHTML(formatOverviewDate(date))}</time>`
        : "";
    return `
        <a class="overview-activity-item" href="${href}">
            <span class="overview-activity-type ${kind}">${label}</span>
            <span class="overview-activity-copy">
                <strong>${escapeHTML(title || "Untitled")}</strong>
                <small>${escapeHTML(description || "")}</small>
            </span>
            ${dateMarkup}
        </a>
    `;
}

function renderOverviewItems(container, items, emptyMessage) {
    if (!container) return;
    container.innerHTML = items.length
        ? items.map(overviewActivityItem).join("")
        : `<p class="overview-empty">${escapeHTML(emptyMessage)}</p>`;
}

async function loadOverviewData() {
    const membersTarget = document.querySelector("#overviewRecentMembers");
    const updatesTarget = document.querySelector("#overviewRecentUpdates");
    const recipesTarget = document.querySelector("#overviewRecentRecipes");
    const [memberResult, messageResult, recipeResult] = await Promise.all([
        recifixApi("/api/admin/members"),
        recifixApi("/api/admin/messages"),
        recifixApi("/api/admin/recipes")
    ]);

    if (memberResult.ok && Array.isArray(memberResult.data.members)) {
        const recentMembers = memberResult.data.members.slice(0, 4).map((member) => ({
            kind: "member",
            label: "MEMBER",
            title: member.name || "New member",
            description: "Joined the community",
            date: member.joined,
            href: "admin-members.html"
        }));
        renderOverviewItems(membersTarget, recentMembers, "No member registrations yet.");
    } else {
        renderOverviewItems(membersTarget, [], memberResult.data.error || "Could not load recent members.");
    }

    const updateItems = [];
    if (messageResult.ok && Array.isArray(messageResult.data.messages)) {
        messageResult.data.messages
            .filter((message) => message.source === "contact")
            .slice(0, 4)
            .forEach((message) => updateItems.push({
                kind: "message",
                label: "MESSAGE",
                title: message.sender_name || "New contact message",
                description: message.subject || "Sent a contact message",
                date: message.created_at,
                href: "admin-messages.html"
            }));
    } else {
        updateItems.push({
            kind: "notice",
            label: "NOTICE",
            title: "Messages unavailable",
            description: messageResult.data.error || "Could not load recent contact messages.",
            date: "",
            href: "admin-messages.html"
        });
    }
    if (recipeResult.ok && Array.isArray(recipeResult.data.recipes)) {
        recipeResult.data.recipes.slice(0, 4).forEach((recipe) => updateItems.push({
            kind: "recipe",
            label: "RECIPE",
            title: recipe.name || "New recipe",
            description: `Added to ${recipe.course || "the recipe collection"}`,
            date: recipe.createdAt,
            href: "admin-recipes.html"
        }));
    } else {
        updateItems.push({
            kind: "notice",
            label: "NOTICE",
            title: "Recipes unavailable",
            description: recipeResult.data.error || "Could not load recent recipes.",
            date: "",
            href: "admin-recipes.html"
        });
    }
    updateItems.sort((a, b) => {
        const dateA = parseOverviewDate(a.date);
        const dateB = parseOverviewDate(b.date);
        return (dateB ? dateB.getTime() : 0) - (dateA ? dateA.getTime() : 0);
    });
    renderOverviewItems(
        updatesTarget,
        updateItems.slice(0, 6),
        "No recent messages or recipes yet."
    );

    if (recipesTarget) {
        if (recipeResult.ok && Array.isArray(recipeResult.data.recipes)) {
            const recentRecipes = recipeResult.data.recipes.slice(0, 4);
            recipesTarget.innerHTML = recentRecipes.length
                ? recentRecipes.map((recipe) => {
                    const image = String(recipe.image || "");
                    const imageSource = safeRecipeImage(image.startsWith("/http") ? image.slice(1) : image);
                    return `
                        <a class="overview-recipe-card" href="admin-recipes.html">
                            <img src="${escapeHTML(imageSource)}" alt="" loading="lazy">
                            <span class="overview-recipe-copy">
                                <strong>${escapeHTML(recipe.name || "Untitled recipe")}</strong>
                                <span>${escapeHTML(recipe.course || "Recipe")}</span>
                                <time datetime="${escapeHTML(overviewDateTime(recipe.createdAt))}">${escapeHTML(formatOverviewDate(recipe.createdAt))}</time>
                            </span>
                        </a>
                    `;
                }).join("")
                : `<p class="overview-empty">No recipes have been added yet.</p>`;
        } else {
            recipesTarget.innerHTML = `<p class="overview-empty">${escapeHTML(recipeResult.data.error || "Could not load recent recipes.")}</p>`;
        }
    }
}

async function loadMembers() {
    const result = await recifixApi("/api/admin/members");
    if (result.ok && result.data.members) {
        members = result.data.members;
        renderMembers();
    }
}

async function changeMemberRole(memberId, newRole) {
    const res = await recifixApi(`/api/admin/members/${memberId}/role`, {
        method: "PATCH",
        body: { role: newRole }
    });
    if (res.ok) {
        await loadMembers();
    } else {
        alert(res.data.error || "Failed to update role.");
        await loadMembers();
    }
}

window.changeMemberRole = changeMemberRole;

function renderMembers() {
    if (!memberBody) return;
    const roleFiltered = activeMemberFilter === "all"
        ? members
        : members.filter((member) => member.role === activeMemberFilter);
    const filteredMembers = roleFiltered.filter((member) =>
        `${member.name} ${member.email}`.toLowerCase().includes(memberSearchQuery)
    );
    document.querySelectorAll("[data-filter-count]").forEach((count) => {
        const role = count.dataset.filterCount;
        count.textContent = String(role === "all" ? members.length : members.filter((member) => member.role === role).length);
    });

    const colors = ["#e9efe2", "#f5e9dd", "#ebe9f3", "#f4e8e4", "#e9efe2", "#f5e9dd", "#ebe9f3"];
    const pageCount = Math.max(1, Math.ceil(filteredMembers.length / membersPerPage));
    memberPage = Math.min(memberPage, pageCount);
    const pageMembers = filteredMembers.slice((memberPage - 1) * membersPerPage, memberPage * membersPerPage);

    memberBody.innerHTML = pageMembers.length ? pageMembers.map((member, idx) => {
        const initials = (member.name || "User").split(' ').map(n => n[0]).join('').toUpperCase().substring(0, 2) || "U";
        const color = colors[idx % colors.length];
        return `
        <tr>
            <td class="member-cell"><span class="member-avatar" style="background:${color};color:#687c61">${escapeHTML(initials)}</span>${escapeHTML(member.name)}</td>
            <td>${escapeHTML(member.email)}</td>
            <td>
                <select class="member-role-select" onchange="changeMemberRole(${member.id}, this.value)" style="padding:4px 8px;border-radius:6px;border:1px solid #dcded5;background:#fff;font-size:13px;cursor:pointer;">
                    <option value="member" ${member.role === 'member' ? 'selected' : ''}>Member</option>
                    <option value="mod" ${member.role === 'mod' ? 'selected' : ''}>Mod</option>
                    <option value="admin" ${member.role === 'admin' ? 'selected' : ''}>Admin</option>
                </select>
            </td>
            <td>${escapeHTML(member.joined)}</td>
            <td><span class="member-status">Active</span></td>
        </tr>`;
    }).join("") : `<tr><td class="no-members" colspan="5">No members match your search.</td></tr>`;
    const countLabel = document.querySelector("#memberCountLabel");
    if (countLabel) {
        const start = filteredMembers.length ? (memberPage - 1) * membersPerPage + 1 : 0;
        const end = Math.min(memberPage * membersPerPage, filteredMembers.length);
        countLabel.textContent = `Showing ${start}–${end} of ${filteredMembers.length} matching members`;
    }
    const pageLabel = document.querySelector("#memberPageLabel");
    if (pageLabel) pageLabel.textContent = `Page ${memberPage} of ${pageCount}`;
    const previous = document.querySelector("#memberPreviousPage");
    const next = document.querySelector("#memberNextPage");
    if (previous) previous.disabled = memberPage <= 1;
    if (next) next.disabled = memberPage >= pageCount;
}

async function loadMessages() {
    const res = await recifixApi("/api/admin/messages");
    if (res.ok && res.data.messages) {
        messages = res.data.messages.map(m => ({
            id: m.id,
            source: m.source || "internal",
            name: m.sender_name,
            email: m.sender_email,
            initials: (m.sender_name || "A").split(' ').map(n => n[0]).join('').toUpperCase().substring(0, 2) || "A",
            subject: m.subject,
            date: m.created_at,
            text: m.body,
            unread: !m.is_read
        }));
        renderMessages();
    }
}

function renderMessages() {
    if (!messageList) return;
    const unread = messages.filter((message) => message.unread).length;
    const read = messages.length - unread;
    const unreadCount = document.querySelector("#unreadCount");
    if (unreadCount) unreadCount.textContent = String(unread).padStart(2, "0");
    const headingCount = document.querySelector("#messageHeadingCount");
    if (headingCount) headingCount.textContent = unread ? `${unread} unread` : "All caught up";
    const allCount = document.querySelector("#allMessageCount");
    const unreadCountLabel = document.querySelector("#unreadMessageCount");
    const readCountLabel = document.querySelector("#readMessageCount");
    if (allCount) allCount.textContent = String(messages.length);
    if (unreadCountLabel) unreadCountLabel.textContent = String(unread);
    if (readCountLabel) readCountLabel.textContent = String(read);
    const filteredMessages = messages
        .map((message, index) => ({ message, index }))
        .filter(({ message }) => activeMessageFilter === "all"
            || (activeMessageFilter === "unread" ? message.unread : !message.unread));
    messageList.innerHTML = filteredMessages.length ? filteredMessages.map(({ message, index }) => `
        <article class="message-item${message.unread ? "" : " read"}">
            <button class="message-open-button" type="button" data-message-index="${index}" aria-label="View message from ${escapeHTML(message.name)}">
                <span class="message-avatar" aria-hidden="true">${escapeHTML(message.initials)}</span>
                <span class="message-copy">
                    <span class="message-meta"><strong>${escapeHTML(message.name)}</strong>${message.source === "contact" ? '<span class="mini-tag warm">CONTACT FORM</span>' : ""}${message.unread ? '<span class="message-new">NEW</span>' : ""}<span class="message-date"><span class="message-date-label">DATE</span><time>${escapeHTML(message.date)}</time></span></span>
                    ${message.email ? `<span class="message-email">${escapeHTML(message.email)}</span>` : ""}
                    <span class="message-subject">${escapeHTML(message.subject)}</span>
                    <span class="message-excerpt">${escapeHTML(message.text).replace(/\n/g, "<br>")}</span>
                </span>
            </button>
            <button class="message-mark-read mark-message-read" type="button" data-message-index="${index}" data-message-source="${message.source}" aria-label="${message.unread ? "Mark" : "Delete"} message from ${escapeHTML(message.name)}${message.unread ? " as read" : ""}">${message.unread ? "Mark as read" : "Delete"}</button>
        </article>`).join("") : `<p class="empty-state">${messages.length ? "No messages in this filter." : "No messages found."}</p>`;
    const navDot = document.querySelector(".nav-dot");
    if (navDot) navDot.hidden = unread === 0;
    const markAllBtn = document.querySelector("#markAllRead");
    if (markAllBtn) markAllBtn.disabled = unread === 0;
}

if (messageList) {
    messageList.addEventListener("click", async (event) => {
        const markButton = event.target.closest(".mark-message-read");
        if (markButton) {
            const message = messages[Number(markButton.dataset.messageIndex)];
            if (!message) return;
            const res = await recifixApi(`/api/admin/messages/${message.id}/read?source=${message.source}`, { method: "PATCH" });
            if (res.ok) await loadMessages();
            else alert(res.data?.error || "Failed to remove message.");
            return;
        }
        const messageButton = event.target.closest(".message-open-button");
        if (messageButton) {
            openMessageDetails(messages[Number(messageButton.dataset.messageIndex)]);
        }
    });
}

const messageDetailsDialog = document.querySelector("#messageDetailsDialog");
function openMessageDetails(message) {
    if (!message || !messageDetailsDialog) return;
    document.querySelector("#messageDetailsTitle").textContent = message.subject || "Message";
    document.querySelector("#messageDetailsMeta").textContent =
        `${message.name || "Unknown sender"}${message.email ? ` · ${message.email}` : ""} · ${message.date || ""}`;
    document.querySelector("#messageDetailsBody").textContent = message.text || "";
    messageDetailsDialog.showModal();
}
document.querySelectorAll("[data-close-message-details]").forEach((button) => {
    button.addEventListener("click", () => messageDetailsDialog.close());
});
if (messageDetailsDialog) {
    messageDetailsDialog.addEventListener("click", (event) => {
        if (event.target === messageDetailsDialog) messageDetailsDialog.close();
    });
}

document.querySelectorAll("[data-message-filter]").forEach((button) => {
    button.addEventListener("click", () => {
        activeMessageFilter = button.dataset.messageFilter;
        document.querySelectorAll("[data-message-filter]").forEach((filter) => {
            const active = filter === button;
            filter.classList.toggle("active", active);
            filter.setAttribute("aria-pressed", String(active));
        });
        renderMessages();
    });
});

const markAllReadButton = document.querySelector("#markAllRead");
if (markAllReadButton) {
    markAllReadButton.addEventListener("click", async () => {
        const unreadMessages = messages.filter((message) => message.unread);
        for (const message of unreadMessages) {
            const res = await recifixApi(`/api/admin/messages/${message.id}/read?source=${message.source}`, { method: "PATCH" });
            if (!res.ok) {
                alert(res.data?.error || "Failed to remove a read message.");
                break;
            }
        }
        await loadMessages();
    });
}

function tags(items, tone = "") {
    if (!Array.isArray(items)) return "";
    return items.map((item) => `<span class="mini-tag ${tone}">${escapeHTML(item)}</span>`).join("");
}

async function loadRecipes() {
    const res = await recifixApi("/api/admin/recipes");
    if (res.ok && res.data.recipes) {
        recipes = res.data.recipes;
        const searchInput = document.querySelector("#recipeSearch");
        renderRecipes(searchInput ? searchInput.value.trim() : "");
    }
}

function renderRecipes(query = "") {
    if (!recipeBody) return;
    const filtered = recipes.filter((recipe) => `${recipe.name} ${recipe.description} ${recipe.flavors.join(" ")} ${recipe.course}`.toLowerCase().includes(query.toLowerCase()));
    const totalRecipesEl = document.querySelector("#totalRecipes");
    if (totalRecipesEl) totalRecipesEl.textContent = String(recipes.length).padStart(2, "0");
    const countLabel = document.querySelector("#recipeCountLabel");
    if (countLabel) countLabel.textContent = `${filtered.length} of ${recipes.length} recipes`;
    recipeBody.innerHTML = filtered.length ? filtered.map((recipe) => `
        <tr>
            <td class="sticky-recipe"><div class="recipe-cell"><img class="recipe-thumb" src="${escapeHTML(recipe.image)}" alt="${escapeHTML(recipe.name)}" loading="lazy"><span><span class="recipe-name">${escapeHTML(recipe.name)}</span><span class="recipe-description">${escapeHTML(recipe.description)}</span></span></div></td>
            <td><div class="cell-tags">${tags(recipe.flavors, "warm")}</div></td>
            <td>${escapeHTML(recipe.course)}</td><td>${escapeHTML(recipe.mealTime)}</td><td class="recipe-time${recipe.timeNeedsReview ? " recipe-time-warning" : ""}"${recipe.timeNeedsReview ? ' title="Edit this recipe to correct the cooking time."' : ""}>${recipe.timeNeedsReview ? "Review time" : escapeHTML(recipe.cookingTime)}</td>
            <td><span class="mini-tag neutral">${escapeHTML(recipe.difficulty)}</span></td><td>${escapeHTML(recipe.servings)}</td>
            <td><div class="cell-tags">${tags(recipe.dietary)}</div></td>
            <td><div class="cell-tags">${tags(recipe.allergens, "warm")}</div></td>
            <td><div class="recipe-ingredients">${Array.isArray(recipe.ingredients) ? recipe.ingredients.map(escapeHTML).join(", ") : ""}</div></td>
            <td>${recipe.steps ? recipe.steps.length : 0} steps</td>
            <td><div class="recipe-actions"><button type="button" class="view-button" data-view-recipe="${recipe.id}">View</button><button type="button" class="edit-button" data-edit-recipe="${recipe.id}">Edit</button><button type="button" class="delete-button" data-delete-recipe="${recipe.id}">Delete</button></div></td>
        </tr>`).join("") : `<tr><td class="no-recipes" colspan="12">No recipes match “${escapeHTML(query)}”. Try another search.</td></tr>`;
}

function openRecipeEditor(recipe = null) {
    if (!recipeEditorDialog || !recipeEditorForm) return;
    editingRecipeId = recipe ? recipe.id : null;
    recipeEditorForm.reset();
    recipeEditorForm.elements.image.value = recipe ? recipe.image : "";
    recipeEditorForm.elements.name.value = recipe ? recipe.name : "";
    recipeEditorForm.elements.description.value = recipe ? recipe.description : "";
    recipeEditorForm.elements.flavors.value = recipe ? recipe.flavors.join(", ") : "";
    recipeEditorForm.elements.course.value = recipe ? recipe.course : "";
    recipeEditorForm.elements.mealTime.value = recipe ? recipe.mealTime.replace(" · ", ", ") : "";
    recipeEditorForm.elements.cookingTime.value = recipe ? recipe.cookingTime : "";
    recipeEditorForm.elements.difficulty.value = recipe ? recipe.difficulty : "Easy";
    recipeEditorForm.elements.servings.value = recipe ? recipe.servings : "";
    recipeEditorForm.elements.dietary.value = recipe ? recipe.dietary.join(", ") : "";
    recipeEditorForm.elements.allergens.value = recipe ? recipe.allergens.join(", ") : "";
    recipeEditorForm.elements.ingredients.value = recipe ? recipe.ingredients.join("\n") : "";
    recipeEditorForm.elements.steps.value = recipe ? recipe.steps.join("\n") : "";
    document.querySelector("#recipeEditorTitle").textContent = recipe ? "Edit recipe" : "Add a recipe";
    document.querySelector("#recipeEditorImagePreview").src = recipe && recipe.image ? recipe.image : "images/intro-image.jpg";
    recipeEditorDialog.showModal();
}

function splitList(value) {
    return value.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
}

function safeRecipeImage(value) {
    const image = value.trim();
    if (!image) return "images/intro-image.jpg";
    if (/^(images\/|\.\/images\/)/i.test(image)) return image.replace(/^\.\//, "");
    try {
        const url = new URL(image, window.location.href);
        return ["http:", "https:"].includes(url.protocol) ? url.href : "images/intro-image.jpg";
    } catch {
        return "images/intro-image.jpg";
    }
}

function formatDate(date) {
    return new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric", year: "numeric" }).format(date);
}

const now = new Date();
const todayLabel = document.querySelector("#todayLabel");
if (todayLabel) todayLabel.textContent = formatDate(now);
const welcomeDate = document.querySelector("#welcomeDate");
if (welcomeDate) welcomeDate.textContent = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(now);

// Load data based on page presence
if (memberBody) loadMembers();
if (messageList) loadMessages();
if (document.querySelector(".nav-count")) {
    loadStats();
    window.setInterval(() => {
        if (!document.hidden) loadStats();
    }, 30000);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) loadStats();
    });
}
if (document.querySelector("#overviewRecentMembers")) loadOverviewData();
if (recipeBody) loadRecipes();

// Account settings loader
async function loadAccountSettings() {
    const res = await recifixApi("/api/auth/me");
    if (res.ok && res.data.user) {
        const u = res.data.user;
        const nameEl = document.getElementById("adminProfileName");
        const emailEl = document.getElementById("adminProfileEmail");
        const twoFactorToggle = document.getElementById("twoFactorToggle");
        const twoFactorStatus = document.getElementById("twoFactorStatus");

        const sidebarName = document.querySelector(".sidebar-admin strong");
        const sidebarAvatar = document.querySelector(".sidebar-admin .avatar");
        const sidebarRole = document.querySelector(".sidebar-admin small");

        if (sidebarName) sidebarName.textContent = u.name || "Admin";
        if (sidebarAvatar) sidebarAvatar.textContent = (u.name || "A")[0].toUpperCase();
        if (sidebarRole) sidebarRole.textContent = (u.role || "admin").charAt(0).toUpperCase() + (u.role || "admin").slice(1);

        const topbarName = document.querySelector(".account-copy strong");
        const topbarAvatar = document.querySelector(".account-button .avatar");
        if (topbarName) topbarName.textContent = u.name || "Admin";
        if (topbarAvatar) topbarAvatar.textContent = (u.name || "A")[0].toUpperCase();
        if (nameEl) nameEl.value = u.name || "";
        if (emailEl) emailEl.value = u.email || "";
        if (twoFactorToggle) {
            twoFactorToggle.checked = Boolean(u.two_factor_enabled);
            if (twoFactorStatus) twoFactorStatus.textContent = u.two_factor_enabled ? "Enabled" : "Not enabled";
        }
    }
}
if (accountSettingsForm) loadAccountSettings();

if (accountSettingsForm) {
    accountSettingsForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("adminProfileName").value.trim();
        const email = document.getElementById("adminProfileEmail").value.trim();
        const status = document.getElementById("profileSettingsStatus");

        const res = await recifixApi("/api/account/settings", {
            method: "PATCH",
            body: { name, email }
        });

        if (res.ok) {
            status.textContent = "Profile updated.";
            status.classList.remove("is-error");
            loadAccountSettings();
        } else {
            status.textContent = res.data.error || "Failed to update profile.";
            status.classList.add("is-error");
        }
    });
}

const settingsPasswordForm = document.querySelector("#settingsPasswordForm");
if (settingsPasswordForm) {
    settingsPasswordForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(settingsPasswordForm);
        const currentPassword = String(formData.get("current_password"));
        const newPassword = String(formData.get("new_password"));
        const confirmPassword = String(formData.get("confirm_password"));
        const status = document.querySelector("#passwordSettingsStatus");
        status.classList.remove("is-error");
        if (newPassword.length < 8) {
            status.textContent = "New password must be at least 8 characters.";
            status.classList.add("is-error");
            return;
        }
        if (newPassword !== confirmPassword) {
            status.textContent = "The new passwords don't match.";
            status.classList.add("is-error");
            return;
        }
        const res = await recifixApi("/api/account/password", {
            method: "POST",
            body: { current_password: currentPassword, new_password: newPassword }
        });
        if (!res.ok) {
            status.textContent = res.data.error || "Failed to update password.";
            status.classList.add("is-error");
            return;
        }
        settingsPasswordForm.reset();
        status.textContent = "Password updated.";
    });
}

const recipeSearch = document.querySelector("#recipeSearch");
if (recipeSearch) {
    recipeSearch.addEventListener("input", (event) => renderRecipes(event.target.value.trim()));
}
document.querySelectorAll("[data-member-filter]").forEach((button) => {
    button.addEventListener("click", () => {
        activeMemberFilter = button.dataset.memberFilter;
        memberPage = 1;
        document.querySelectorAll("[data-member-filter]").forEach((filter) => {
            const isActive = filter === button;
            filter.classList.toggle("active", isActive);
            filter.setAttribute("aria-pressed", String(isActive));
        });
        renderMembers();
    });
});
const memberSearch = document.querySelector("#memberSearch");
if (memberSearch) {
    memberSearch.addEventListener("input", () => {
        memberSearchQuery = memberSearch.value.trim().toLowerCase();
        memberPage = 1;
        renderMembers();
    });
}
const memberPreviousPage = document.querySelector("#memberPreviousPage");
const memberNextPage = document.querySelector("#memberNextPage");
if (memberPreviousPage) memberPreviousPage.addEventListener("click", () => {
    memberPage = Math.max(1, memberPage - 1);
    renderMembers();
});
if (memberNextPage) memberNextPage.addEventListener("click", () => {
    memberPage += 1;
    renderMembers();
});

if (recipeBody) {
    recipeBody.addEventListener("click", async (event) => {
        const editButton = event.target.closest("[data-edit-recipe]");
        const deleteButton = event.target.closest("[data-delete-recipe]");
        if (editButton) {
            const recipe = recipes.find((item) => item.id === Number(editButton.dataset.editRecipe));
            if (recipe) openRecipeEditor(recipe);
        }
        if (deleteButton) {
            const recipeId = Number(deleteButton.dataset.deleteRecipe);
            const recipe = recipes.find((item) => item.id === recipeId);
            if (!recipe || !window.confirm(`Delete “${recipe.name}”?`)) return;
            const res = await recifixApi(`/api/admin/recipes/${recipeId}`, { method: "DELETE" });
            if (res.ok) {
                await loadRecipes();
                await loadStats();
            } else {
                alert(res.data.error || "Failed to delete recipe.");
            }
        }
    });
}

if (recipeEditorForm) {
    recipeEditorForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(recipeEditorForm);
        const recipeData = {
            name: String(formData.get("name")).trim(),
            image: safeRecipeImage(String(formData.get("image"))),
            description: String(formData.get("description")).trim(),
            flavors: splitList(String(formData.get("flavors"))),
            course: String(formData.get("course")).trim(),
            mealTime: splitList(String(formData.get("mealTime"))).join(" · "),
            cookingTime: String(formData.get("cookingTime")).trim(),
            difficulty: String(formData.get("difficulty")),
            servings: String(formData.get("servings")).trim(),
            dietary: splitList(String(formData.get("dietary"))),
            allergens: splitList(String(formData.get("allergens"))),
            ingredients: splitList(String(formData.get("ingredients"))),
            steps: splitList(String(formData.get("steps")))
        };

        let res;
        if (editingRecipeId === null) {
            res = await recifixApi("/api/admin/recipes", { method: "POST", body: recipeData });
        } else {
            res = await recifixApi(`/api/admin/recipes/${editingRecipeId}`, { method: "PUT", body: recipeData });
        }

        if (res.ok) {
            recipeEditorDialog.close();
            await loadRecipes();
            await loadStats();
        } else {
            alert(res.data.error || "Failed to save recipe.");
        }
    });
}

const addRecipeButton = document.querySelector("#addRecipeButton");
if (addRecipeButton) {
    addRecipeButton.addEventListener("click", () => openRecipeEditor());
}

document.querySelectorAll("[data-close-editor]").forEach((button) => button.addEventListener("click", () => recipeEditorDialog.close()));
if (recipeEditorDialog) {
    recipeEditorDialog.addEventListener("click", (event) => {
        if (event.target === recipeEditorDialog) recipeEditorDialog.close();
    });
}

if (recipeEditorForm) {
    recipeEditorForm.elements.image.addEventListener("input", (event) => {
        document.querySelector("#recipeEditorImagePreview").src = safeRecipeImage(event.target.value);
    });
}

const themeToggle = document.querySelector(".theme-toggle");
function setTheme(isDark, save = true) {
    if (!themeToggle) return;
    document.body.classList.toggle("dark-mode", isDark);
    document.documentElement.classList.toggle("dark-mode", isDark);
    themeToggle.setAttribute("aria-pressed", String(isDark));
    themeToggle.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
    themeToggle.querySelector("img").src = isDark ? "images/icons/darkmode.svg" : "images/icons/lightmode.svg";
    if (save) localStorage.setItem("recifix-theme", isDark ? "dark" : "light");
}
if (themeToggle) {
    setTheme(localStorage.getItem("recifix-theme") === "dark", false);
    themeToggle.addEventListener("click", () => setTheme(!document.body.classList.contains("dark-mode")));
}

// Send message dialog logic
const sendMessageDialog = document.querySelector("#sendMessageDialog");
const sendMessageForm = document.querySelector("#sendMessageForm");
const openSendMessageBtn = document.querySelector(".send-message-button");

if (openSendMessageBtn) {
    openSendMessageBtn.addEventListener("click", () => {
        if (sendMessageDialog) {
            sendMessageForm.reset();
            sendMessageDialog.hidden = false;
            sendMessageDialog.showModal();
        }
    });
}

const twoFactorToggleEl = document.getElementById("twoFactorToggle");
const twoFactorStatusEl = document.getElementById("twoFactorStatus");
const twoFactorSetupDialog = document.querySelector("#twoFactorSetupDialog");
const twoFactorSetupForm = document.querySelector("#twoFactorSetupForm");
const twoFactorQRImg = document.querySelector("#twoFactorQR");
const twoFactorSecretInput = document.querySelector("#twoFactorSecret");
let currentTwoFactorSecret = null;

function open2FASetup() {
    if (twoFactorSetupDialog && twoFactorSetupForm) {
        twoFactorSetupForm.reset();
        currentTwoFactorSecret = null;
        recifixApi("/api/account/2fa/setup", { method: "POST" })
            .then(res => {
                if (res.ok && res.data.secret) {
                    currentTwoFactorSecret = res.data.secret;
                    twoFactorSecretInput.value = res.data.secret;
                    const otpauthUrl = res.data.otpauth_url;
                    const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(otpauthUrl)}&size=180x180`;
                    twoFactorQRImg.src = qrUrl;
                    twoFactorSetupDialog.hidden = false;
                    twoFactorSetupDialog.showModal();
                }
            });
    }
}

function verify2FA(code) {
    if (!currentTwoFactorSecret) return;
    recifixApi("/api/account/2fa/verify", {
        method: "POST",
        body: { secret: currentTwoFactorSecret, code }
    })
    .then(res => {
        if (res.ok) {
            alert("Two-factor authentication enabled successfully!");
            twoFactorToggleEl.checked = true;
            twoFactorStatusEl.textContent = "Enabled";
            twoFactorSetupDialog.close();
        } else {
            alert(res.data.error || "Invalid verification code.");
        }
    });
}

if (twoFactorToggleEl && twoFactorStatusEl) {
    twoFactorToggleEl.addEventListener("change", async () => {
        if (twoFactorToggleEl.checked) {
            twoFactorToggleEl.checked = false;
            const confirmed = confirm("Turn on two-factor authentication? You will scan a QR code with an authenticator app, and that code will be required at login.");
            if (confirmed) {
                open2FASetup();
            }
            return;
        }

        const code = window.prompt("Enter the 6-digit code from your authenticator app to turn off 2FA.");
        if (!code) {
            twoFactorToggleEl.checked = true;
            twoFactorStatusEl.textContent = "Enabled";
            return;
        }
        const res = await recifixApi("/api/account/2fa/disable", {
            method: "POST",
            body: { code: code.trim() }
        });
        if (res.ok) {
            twoFactorToggleEl.checked = false;
            twoFactorStatusEl.textContent = "Not enabled";
            alert("Two-factor authentication is off. Login will only ask for your password.");
            return;
        }
        twoFactorToggleEl.checked = true;
        twoFactorStatusEl.textContent = "Enabled";
        alert(res.data.error || "Could not turn off 2FA.");
    });
}

function showStatus(msg, isError) {
    alert(msg);
}
function closeSendMessageDialog() {
    if (sendMessageDialog) {
        sendMessageDialog.hidden = true;
        sendMessageDialog.close();
    }
}
function sendMessage() {
    const subjectInput = sendMessageForm.querySelector('input[name="subject"]');
    const bodyInput = sendMessageForm.querySelector('textarea[name="body"]');
    const subject = (subjectInput ? subjectInput.value : "").trim();
    const body = (bodyInput ? bodyInput.value : "").trim();
    if (!subject || !body) {
        alert("Subject and body are required.");
        return;
    }
    recifixApi("/api/admin/messages", { method: "POST", body: { subject, body } })
    .then(res => {
        if (res.ok) {
            alert("Message sent successfully!");
            sendMessageForm.reset();
            closeSendMessageDialog();
            loadMessages();
            loadStats();
        } else {
            alert(res.data.error || "Failed to send message.");
        }
    });
}
document.querySelectorAll("[data-close-message]").forEach(btn => {
    btn.addEventListener("click", closeSendMessageDialog);
});
if (sendMessageDialog) {
    sendMessageDialog.addEventListener("click", (e) => {
        if (e.target === sendMessageDialog) closeSendMessageDialog();
    });
}
if (sendMessageForm) {
    sendMessageForm.addEventListener("submit", (e) => {
        e.preventDefault();
        sendMessage();
    });
}

// 2FA Setup dialog handlers
function close2FADialog() {
    if (twoFactorSetupDialog) {
        twoFactorSetupDialog.hidden = true;
        twoFactorSetupDialog.close();
        currentTwoFactorSecret = null;
    }
}
if (twoFactorSetupForm) {
    twoFactorSetupForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const codeInput = twoFactorSetupForm.querySelector('input[name="code"]');
        const code = (codeInput ? codeInput.value : "").trim();
        if (code.length === 6 && /^\d{6}$/.test(code)) {
            verify2FA(code);
        } else {
            alert("Please enter a valid 6-digit code.");
        }
    });
}
document.querySelectorAll("[data-close-2fa]").forEach(btn => {
    btn.addEventListener("click", () => {
        close2FADialog();
        if (twoFactorToggleEl) twoFactorToggleEl.checked = false;
    });
});
if (twoFactorSetupDialog) {
    twoFactorSetupDialog.addEventListener("click", (e) => {
        if (e.target === twoFactorSetupDialog) close2FADialog();
    });
}
