// SPDX-License-Identifier: GPL-2.0
/*
 * AnnePro2 BLE HID descriptor fixup driver.
 *
 * The AnnePro2 BLE firmware sends a 44-byte descriptor with an Application
 * Collection that is never closed.  The original trim-to-last-balanced-depth
 * approach left only the 4-byte header (Usage Page + Usage) — no Collection,
 * no Input items — so the HID core never created an input device.
 *
 * Replace the malformed descriptor with a standard 6KRO boot-keyboard
 * descriptor instead.
 */
#include <linux/module.h>
#include <linux/hid.h>

static const u8 annepro2_rdesc_fixed[] = {
	0x05, 0x01,        /* Usage Page (Generic Desktop) */
	0x09, 0x06,        /* Usage (Keyboard) */
	0xA1, 0x01,        /* Collection (Application) */
	/* Modifier keys: 8 x 1-bit */
	0x05, 0x07,        /*   Usage Page (Key Codes) */
	0x19, 0xE0,        /*   Usage Minimum (224) */
	0x29, 0xE7,        /*   Usage Maximum (231) */
	0x15, 0x00,        /*   Logical Minimum (0) */
	0x25, 0x01,        /*   Logical Maximum (1) */
	0x75, 0x01,        /*   Report Size (1) */
	0x95, 0x08,        /*   Report Count (8) */
	0x81, 0x02,        /*   Input (Data, Variable, Absolute) */
	/* Reserved byte */
	0x95, 0x01,        /*   Report Count (1) */
	0x75, 0x08,        /*   Report Size (8) */
	0x81, 0x01,        /*   Input (Constant) */
	/* Key array: 6 x 8-bit keycodes */
	0x95, 0x06,        /*   Report Count (6) */
	0x75, 0x08,        /*   Report Size (8) */
	0x15, 0x00,        /*   Logical Minimum (0) */
	0x25, 0xFF,        /*   Logical Maximum (255) */
	0x05, 0x07,        /*   Usage Page (Key Codes) */
	0x19, 0x00,        /*   Usage Minimum (0) */
	0x29, 0xFF,        /*   Usage Maximum (255) */
	0x81, 0x00,        /*   Input (Data, Array) */
	0xC0,              /* End Collection */
};

static const u8 *hid_annepro2_report_fixup(struct hid_device *hdev, u8 *rdesc,
					    unsigned int *rsize)
{
	hid_info(hdev,
		 "replacing malformed HID descriptor (%u bytes) with fixed 6KRO descriptor\n",
		 *rsize);
	*rsize = sizeof(annepro2_rdesc_fixed);
	return annepro2_rdesc_fixed;
}

static int hid_annepro2_probe(struct hid_device *hdev,
			      const struct hid_device_id *id)
{
	int ret;

	ret = hid_parse(hdev);
	if (ret)
		return ret;

	return hid_hw_start(hdev, HID_CONNECT_DEFAULT);
}

static const struct hid_device_id hid_annepro2_table[] = {
	{ HID_BLUETOOTH_DEVICE(0x000D, 0x0000) },
	{ }
};
MODULE_DEVICE_TABLE(hid, hid_annepro2_table);

static struct hid_driver hid_annepro2 = {
	.name		= "hid-annepro2",
	.id_table	= hid_annepro2_table,
	.report_fixup	= hid_annepro2_report_fixup,
	.probe		= hid_annepro2_probe,
};

module_hid_driver(hid_annepro2);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("AnnePro2 BLE HID descriptor fixup");
MODULE_AUTHOR("local fix");
