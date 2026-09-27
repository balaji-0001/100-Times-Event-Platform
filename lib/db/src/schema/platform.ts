import {
  boolean,
  date,
  index,
  integer,
  numeric,
  pgTable,
  serial,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const usersTable = pgTable(
  "users",
  {
    id: serial("id").primaryKey(),
    name: text("name").notNull(),
    email: text("email").notNull(),
    passwordHash: text("password_hash").notNull(),
    role: text("role").notNull().default("USER"),
    country: text("country"),
    jobTitle: text("job_title"),
    company: text("company"),
    bio: text("bio"),
    profileImage: text("profile_image"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("users_email_idx").on(table.email)],
);

export const categoriesTable = pgTable("categories", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  slug: text("slug").notNull(),
  description: text("description").notNull(),
  icon: text("icon").notNull(),
  image: text("image"),
});

export const citiesTable = pgTable("cities", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  slug: text("slug").notNull(),
  country: text("country").notNull(),
  description: text("description"),
  image: text("image"),
});

export const organizersTable = pgTable("organizers", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  slug: text("slug").notNull(),
  description: text("description").notNull(),
  logo: text("logo"),
  website: text("website"),
  email: text("email"),
  phone: text("phone"),
});

export const venuesTable = pgTable(
  "venues",
  {
    id: serial("id").primaryKey(),
    name: text("name").notNull(),
    slug: text("slug").notNull(),
    address: text("address").notNull(),
    cityId: integer("city_id"),
    country: text("country").notNull(),
    capacity: integer("capacity"),
    description: text("description"),
    image: text("image"),
  },
  (table) => [index("venues_city_idx").on(table.cityId)],
);

export const eventsTable = pgTable(
  "events",
  {
    id: serial("id").primaryKey(),
    title: text("title").notNull(),
    slug: text("slug").notNull(),
    description: text("description").notNull(),
    eventType: text("event_type").notNull(),
    startDate: date("start_date", { mode: "string" }).notNull(),
    endDate: date("end_date", { mode: "string" }).notNull(),
    startTime: text("start_time").notNull(),
    endTime: text("end_time"),
    price: numeric("price").notNull().default("0"),
    image: text("image"),
    status: text("status").notNull().default("draft"),
    format: text("format").notNull().default("in-person"),
    categoryId: integer("category_id"),
    organizerId: integer("organizer_id"),
    venueId: integer("venue_id"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex("events_slug_idx").on(table.slug),
    index("events_start_date_idx").on(table.startDate),
    index("events_category_idx").on(table.categoryId),
    index("events_organizer_idx").on(table.organizerId),
  ],
);

export const speakersTable = pgTable("speakers", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  slug: text("slug").notNull(),
  title: text("title").notNull(),
  company: text("company").notNull(),
  biography: text("biography"),
  image: text("image"),
  expertise: text("expertise").array().notNull().default([]),
});

export const reviewsTable = pgTable(
  "reviews",
  {
    id: serial("id").primaryKey(),
    eventId: integer("event_id").notNull(),
    userId: integer("user_id").notNull(),
    rating: integer("rating").notNull(),
    title: text("title").notNull(),
    comment: text("comment").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex("reviews_event_user_idx").on(table.eventId, table.userId),
    index("reviews_event_idx").on(table.eventId),
  ],
);

export const registrationsTable = pgTable(
  "registrations",
  {
    id: serial("id").primaryKey(),
    eventId: integer("event_id").notNull(),
    userId: integer("user_id").notNull(),
    ticketType: text("ticket_type").notNull(),
    status: text("status").notNull().default("confirmed"),
    registeredAt: timestamp("registered_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex("registrations_event_user_idx").on(table.eventId, table.userId),
    index("registrations_user_idx").on(table.userId),
  ],
);

export const savedEventsTable = pgTable(
  "saved_events",
  {
    userId: integer("user_id").notNull(),
    eventId: integer("event_id").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("saved_events_user_event_idx").on(table.userId, table.eventId)],
);

export const notificationsTable = pgTable("notifications", {
  id: serial("id").primaryKey(),
  userId: integer("user_id").notNull(),
  title: text("title").notNull(),
  message: text("message").notNull(),
  isRead: boolean("is_read").notNull().default(false),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertUserSchema = createInsertSchema(usersTable).omit({ id: true, createdAt: true });
export const insertEventSchema = createInsertSchema(eventsTable).omit({ id: true, createdAt: true });
export const insertReviewSchema = createInsertSchema(reviewsTable).omit({ id: true, createdAt: true });
export type User = typeof usersTable.$inferSelect;
export type Event = typeof eventsTable.$inferSelect;
export type Review = typeof reviewsTable.$inferSelect;
export type InsertUser = z.infer<typeof insertUserSchema>;
export type InsertEvent = z.infer<typeof insertEventSchema>;
export type InsertReview = z.infer<typeof insertReviewSchema>;