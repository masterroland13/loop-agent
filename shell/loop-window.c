/* Loop Agent window. Blocks until the user closes it. */
#include <gtk/gtk.h>
#include <stdio.h>
#include <webkit2/webkit2.h>

static GtkWidget *g_view = NULL;
static GtkWidget *g_window = NULL;
static int last_px = -99999;
static int last_py = -99999;

static void apply_left_ptr(GdkWindow *win, GdkCursor *cursor) {
    GList *children;
    GList *iter;

    if (win == NULL) {
        return;
    }
    gdk_window_set_cursor(win, cursor);
    children = gdk_window_get_children(win);
    for (iter = children; iter != NULL; iter = iter->next) {
        apply_left_ptr(GDK_WINDOW(iter->data), cursor);
    }
    g_list_free(children);
}

static void refresh_cursors(void) {
    GdkWindow *win;
    GdkCursor *cursor;

    if (g_window == NULL) {
        return;
    }
    win = gtk_widget_get_window(g_window);
    if (win == NULL) {
        return;
    }
    cursor = gdk_cursor_new_for_display(gdk_window_get_display(win), GDK_LEFT_PTR);
    if (cursor == NULL) {
        return;
    }
    apply_left_ptr(win, cursor);
    g_object_unref(cursor);
}

static gboolean poll_pointer(gpointer data) {
    gint root_x = 0;
    gint root_y = 0;
    gint origin_x = 0;
    gint origin_y = 0;
    gint x = 0;
    gint y = 0;
    gint width = 0;
    gint height = 0;
    gint scale = 1;
    char script[160];
    GdkWindow *win;
    GdkDisplay *display;
    GdkSeat *seat;
    GdkDevice *pointer;

    (void)data;
    if (g_view == NULL || !gtk_widget_get_realized(g_view)) {
        return TRUE;
    }
    win = gtk_widget_get_window(g_view);
    if (win == NULL) {
        return TRUE;
    }
    display = gdk_window_get_display(win);
    seat = gdk_display_get_default_seat(display);
    pointer = gdk_seat_get_pointer(seat);
    gdk_device_get_position(pointer, NULL, &root_x, &root_y);
    gdk_window_get_origin(win, &origin_x, &origin_y);
    x = root_x - origin_x;
    y = root_y - origin_y;
    width = gtk_widget_get_allocated_width(g_view);
    height = gtk_widget_get_allocated_height(g_view);
    if (x < 0 || y < 0 || x >= width || y >= height) {
        x = -1;
        y = -1;
    }
    if (x == last_px && y == last_py) {
        return TRUE;
    }
    last_px = x;
    last_py = y;
    scale = gtk_widget_get_scale_factor(g_view);
    if (scale < 1) {
        scale = 1;
    }
    if (x < 0) {
        snprintf(script, sizeof(script), "window.__loopPointer&&window.__loopPointer(-1,-1)");
    } else {
        snprintf(
            script,
            sizeof(script),
            "window.__loopPointer&&window.__loopPointer(%d,%d)",
            x / scale,
            y / scale
        );
    }
    webkit_web_view_run_javascript(WEBKIT_WEB_VIEW(g_view), script, NULL, NULL, NULL);
    refresh_cursors();
    return TRUE;
}

static void on_destroy(GtkWidget *widget, gpointer data) {
    (void)widget;
    (void)data;
    gtk_main_quit();
}

static gboolean on_load_failed(
    WebKitWebView *view,
    WebKitLoadEvent event,
    gchar *failing_uri,
    GError *error,
    gpointer data
) {
    (void)view;
    (void)event;
    (void)data;
    fprintf(
        stderr,
        "loop-window load failed: %s (%s)\n",
        failing_uri ? failing_uri : "?",
        error && error->message ? error->message : "unknown"
    );
    return FALSE;
}

static void show_cursor(GtkWidget *widget, gpointer data) {
    GdkWindow *win;
    GdkCursor *cursor;

    (void)data;
    win = gtk_widget_get_window(widget);
    if (win == NULL) {
        return;
    }
    cursor = gdk_cursor_new_from_name(gtk_widget_get_display(widget), "default");
    if (cursor == NULL) {
        return;
    }
    gdk_window_set_cursor(win, cursor);
    g_object_unref(cursor);
}

int main(int argc, char **argv) {
    const char *url = (argc > 1 && argv[1][0] != '\0') ? argv[1] : "about:blank";

    g_setenv("GDK_BACKEND", "x11", TRUE);
    g_unsetenv("WAYLAND_DISPLAY");
    g_setenv("WEBKIT_DISABLE_COMPOSITING_MODE", "1", TRUE);
    g_setenv("WEBKIT_DISABLE_DMABUF_RENDERER", "1", TRUE);
    gtk_init(&argc, &argv);
    fprintf(
        stderr,
        "loop-window display=%s\n",
        gdk_display_get_name(gdk_display_get_default())
    );

    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    g_window = window;
    gtk_window_set_title(GTK_WINDOW(window), "Loop Agent");
    gtk_window_set_default_size(GTK_WINDOW(window), 1280, 800);
    gtk_window_unmaximize(GTK_WINDOW(window));

    GdkScreen *screen = gtk_window_get_screen(GTK_WINDOW(window));
    if (screen != NULL) {
        fprintf(
            stderr,
            "loop-window screen %dx%d url=%s\n",
            gdk_screen_get_width(screen),
            gdk_screen_get_height(screen),
            url
        );
    }

    GtkWidget *view = webkit_web_view_new();
    g_view = view;
    WebKitSettings *wk_settings = webkit_web_view_get_settings(WEBKIT_WEB_VIEW(view));
    webkit_settings_set_enable_javascript(wk_settings, TRUE);
    webkit_settings_set_hardware_acceleration_policy(
        wk_settings, WEBKIT_HARDWARE_ACCELERATION_POLICY_NEVER);
    webkit_settings_set_enable_write_console_messages_to_stdout(wk_settings, TRUE);
    g_signal_connect(view, "load-failed", G_CALLBACK(on_load_failed), NULL);

    gtk_widget_set_can_focus(view, TRUE);
    gtk_widget_add_events(
        view,
        GDK_POINTER_MOTION_MASK
            | GDK_BUTTON_PRESS_MASK
            | GDK_BUTTON_RELEASE_MASK
            | GDK_ENTER_NOTIFY_MASK
            | GDK_LEAVE_NOTIFY_MASK);
    gtk_container_set_border_width(GTK_CONTAINER(window), 0);
    gtk_container_add(GTK_CONTAINER(window), view);
    webkit_web_view_load_uri(WEBKIT_WEB_VIEW(view), url);

    g_signal_connect(window, "destroy", G_CALLBACK(on_destroy), NULL);
    g_signal_connect(window, "realize", G_CALLBACK(show_cursor), NULL);
    g_signal_connect(view, "realize", G_CALLBACK(show_cursor), NULL);
    gtk_widget_show_all(window);
    gtk_window_resize(GTK_WINDOW(window), 1280, 800);
    gtk_widget_grab_focus(view);
    g_timeout_add(33, poll_pointer, NULL);
    gtk_main();
    return 0;
}
